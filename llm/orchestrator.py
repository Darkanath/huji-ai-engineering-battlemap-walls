"""The chunked pass's orchestrator: split a map into chunks, trace each with its own agent at the
same time, merge the answers by fixed rules, and have an orchestrator model review the seams.

Design and reasons: specs/002-chunked-map-tracing/ (research.md R2-R9, contracts/orchestrator.md).
The agents are the measured tool loop of `llm.agent.trace_map`, run on a window of the map;
the merge is `llm.merge` (no model call); the seam review is `llm.review`.
"""

import threading
import time
import tomllib
from collections.abc import Callable
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field
from enum import StrEnum
from pathlib import Path

import anthropic
from PIL import Image

from llm.agent import CONFIG, Trace, _time_left, trace_map
from llm.merge import (  # Chunk and chunk_layout are re-exported: the layout lives in merge
    Chunk,
    MergeReport,
    Seam,
    apply_review,
    chunk_layout,
    merge_answers,
    seams,
)
from llm.review import ReviewRun, ReviewState, review_seams
from llm.views import Box

__all__ = [
    "Chunk",
    "ChunkRun",
    "ChunkState",
    "ChunkedTrace",
    "chunk_layout",
    "default_agents",
    "load_chunked_config",
    "trace_chunks",
]

MODEL_KEYS = ("name", "label", "effort", "max_tokens", "fallbacks")  # what the tool loop reads


def _model(entry: dict) -> dict:
    """The model fields of one `[chunked.agents.*]` entry, in the form `cfg["model"]` takes."""
    return {key: entry[key] for key in MODEL_KEYS}


def default_agents(path: Path = CONFIG) -> str:
    """The selector's default choice, `[chunked].default_agents`."""
    return tomllib.loads(Path(path).read_text())["chunked"]["default_agents"]


def load_chunked_config(agents: str, path: Path = CONFIG) -> dict:
    """The tool loops' settings for a chunked pass whose agents use the `agents` choice.

    The result has the shape `llm.agent.load_config` gives (so `trace_map` takes it as is),
    with three differences: `cfg["model"]` is the chosen agents' model, `cfg["limits"]` is
    `[chunked.limits]`, and `cfg["review"]` holds the orchestrator's model (the entry the
    choice's `orchestrator` names) plus `[chunked.review]`. `cfg["chunked"]` holds the
    `[chunked]` settings with the choice's name, part size (`core_squares`), orchestrator,
    deadline and cost limit.
    Raises ValueError for a choice that is not in `[chunked.agents]`.
    """
    cfg = tomllib.loads(Path(path).read_text())
    chunked = cfg["chunked"]
    choices = chunked["agents"]
    if agents not in choices:
        raise ValueError(f"unknown agents choice {agents!r}; expected one of {sorted(choices)}")
    entry = choices[agents]
    cfg["model"] = _model(entry)
    cfg["limits"] = dict(chunked["limits"])
    cfg["review"] = {"model": _model(choices[entry["orchestrator"]]), **chunked["review"]}
    settings = {k: v for k, v in chunked.items() if not isinstance(v, dict)}
    settings.update(
        agents=agents,
        core_squares=entry["core_squares"],
        orchestrator=entry["orchestrator"],
        deadline_s=entry["deadline_s"],
        max_cost_usd=entry["max_cost_usd"],
        expected_seconds_per_chunk=entry["expected_seconds_per_chunk"],
        expected_cost_per_chunk_usd=entry["expected_cost_per_chunk_usd"],
        merge=dict(chunked["merge"]),
    )
    cfg["chunked"] = settings
    return cfg


class ChunkState(StrEnum):
    """Where one chunk agent stands. `done`, `failed` and `skipped` are final."""

    waiting = "waiting"
    tracing = "tracing"
    done = "done"  # ended with an answer (also "kept last submission" after an error)
    failed = "failed"  # ended with no answer
    skipped = "skipped"  # never started: the pass's deadline or cost limit was used up


@dataclass
class ChunkRun:
    """One chunk agent: its chunk, how it ended, and its own trace."""

    chunk: Chunk
    state: ChunkState = ChunkState.waiting
    trace: Trace = field(default_factory=Trace)
    seconds: float = 0.0
    error: BaseException | None = None  # what ended it, if anything; the app classifies it

    def counts(self) -> dict[str, int]:
        """Walls (polylines and arcs), portals and lights in this agent's own answer."""
        a = self.trace.answer or {}
        return {
            "walls": len(a.get("walls", [])) + len(a.get("arcs", [])),
            "portals": len(a.get("portals", [])),
            "lights": len(a.get("lights", [])),
        }


@dataclass
class ChunkedTrace:
    """Everything a chunked pass produced: per-chunk runs, the merge, the review, the answer."""

    layout: list[Chunk]
    seams: list[Seam]
    runs: list[ChunkRun]
    merged: dict | None = None  # the rule-merged answer; None when no chunk is done
    merge: MergeReport | None = None
    review: ReviewRun = field(default_factory=lambda: ReviewRun(ReviewState.not_needed))
    answer: dict | None = None  # final: merged with the review applied, or merged
    cost_usd: float = 0.0
    seconds: float = 0.0

    def by_state(self, state: ChunkState) -> list[ChunkRun]:
        """The runs that ended in `state`."""
        return [r for r in self.runs if r.state == state]

    @property
    def untraced(self) -> list[Box]:
        """The cores of the chunks with no answer."""
        return [r.chunk.core for r in self.runs if r.state != ChunkState.done]


Update = Callable[[str, int | None, str], None]


def trace_chunks(
    image: Image.Image,
    map_size: tuple[int, int],
    cfg: dict,
    client: anthropic.Anthropic,
    deadline: float | None = None,
    on_update: Update | None = None,
    out_dir: Path | None = None,
    spent_before: float = 0.0,
) -> ChunkedTrace:
    """Run a chunked pass: agents on every chunk at the same time, merge, seam review.

    `cfg` is `load_chunked_config`'s. Up to `max_parallel` agents run at once, sharing
    `client` and `deadline` (a time.monotonic() value). A chunk is skipped when, as it is
    about to start, the deadline has passed or the chunks so far have cost the choice's
    `max_cost_usd`. `on_update(kind, index, state)` is told every change ("chunk" with the
    chunk's index, or "review" with None); it is called from worker threads, and anything it
    raises is ignored. With `out_dir`, the images every agent and the reviewer saw are saved
    under `chunks/<i>/views/` and `review/views/`. `spent_before` is what the pass already
    spent (the map-size step); it counts toward the cost limit but not toward the result's
    `cost_usd`, which is the agents' and the review's. The review gets only the budget the
    agents left. Never raises for an agent's or the review's failure: those end in the runs'
    states.
    """
    start = time.monotonic()
    settings = cfg["chunked"]
    layout = chunk_layout(
        map_size, settings["core_squares"], settings["overlap_squares"], settings["max_per_side"]
    )
    seam_list = seams(layout, map_size, cfg["review"]["strip_squares"])
    runs = [ChunkRun(chunk) for chunk in layout]
    lock = threading.Lock()

    def notify(kind: str, index: int | None, state: str) -> None:
        """Tell the caller about a change; its errors never reach the pass."""
        if on_update is not None:
            try:
                on_update(kind, index, state)
            except Exception:  # noqa: BLE001 - a page callback must not break the pass
                pass

    def agents_spent() -> float:
        """What the agents have cost so far (their traces update while they run)."""
        return sum(r.trace.cost_usd for r in runs)

    def spent() -> float:
        """What the pass has cost so far, counting what was spent before the agents."""
        return spent_before + agents_spent()

    def out_of_budget() -> bool:
        """Whether the deadline has passed or the agents have cost the limit."""
        left = _time_left(deadline)
        return (left is not None and left <= 0) or spent() >= settings["max_cost_usd"]

    def work(run: ChunkRun) -> None:
        """Trace one chunk, unless the pass is out of time or budget."""
        with lock:
            run.state = ChunkState.skipped if out_of_budget() else ChunkState.tracing
        notify("chunk", run.chunk.index, run.state)
        if run.state == ChunkState.skipped:
            return
        began = time.monotonic()
        views = out_dir / "chunks" / str(run.chunk.index) / "views" if out_dir else None
        try:
            trace_map(
                image,
                map_size,
                cfg,
                client,
                views_dir=views,
                deadline=deadline,
                trace=run.trace,
                window=run.chunk.window,
                core=run.chunk.core,
            )
        except Exception as error:  # noqa: BLE001 - every cause ends this chunk, not the pass
            run.error = error
        run.seconds = time.monotonic() - began
        run.state = ChunkState.done if run.trace.answer is not None else ChunkState.failed
        notify("chunk", run.chunk.index, run.state)

    with ThreadPoolExecutor(max_workers=settings["max_parallel"]) as pool:
        list(pool.map(work, runs))

    result = ChunkedTrace(layout=layout, seams=seam_list, runs=runs)
    merge_cfg = settings["merge"]
    tolerance, min_piece = merge_cfg["join_tolerance_squares"], merge_cfg["min_piece_squares"]
    answers = {r.chunk.index: r.trace.answer for r in runs if r.state == ChunkState.done}
    if answers:
        result.merged, result.merge = merge_answers(layout, answers, map_size, tolerance, min_piece)
        result.answer = result.merged
    if len(layout) > 1:
        if not answers or out_of_budget():
            result.review = ReviewRun(ReviewState.skipped, model=cfg["review"]["model"]["name"])
        else:
            notify("review", None, ReviewState.reviewing)
            views = out_dir / "review" / "views" if out_dir else None
            left = settings["max_cost_usd"] - spent()
            review_cfg = {
                **cfg,
                "review": {
                    **cfg["review"],
                    "max_cost_usd": min(cfg["review"]["max_cost_usd"], left),
                },
            }
            result.review = review_seams(
                image, map_size, result.merged, seam_list, review_cfg, client, deadline, views
            )
            if result.review.state == ReviewState.done:
                strips = [s.strip for s in seam_list]
                result.answer, result.review.removed, result.review.added = apply_review(
                    result.merged,
                    result.review.trace.answer,
                    strips,
                    map_size,
                    tolerance,
                    min_piece,
                )
        notify("review", None, result.review.state)
    result.cost_usd = agents_spent() + result.review.trace.cost_usd
    result.seconds = time.monotonic() - start
    return result
