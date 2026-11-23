"""The orchestrator model's seam review: the last step of the chunked pass.

After the rule-based merge (`llm.merge.merge_answers`), one model looks only at the strips
along the borders between chunks, the one place where separate agents' work was joined and
no single agent saw both sides. It gets close-up crops of every strip with the merged lines
drawn on them and a listing of what lies there, and submits the complete content the strips
should have. The orchestrator then applies it with `llm.merge.apply_review`, which cannot
change anything outside the strips.

Design: specs/002-chunked-map-tracing/research.md R6; contract: contracts/orchestrator.md.
"""

import json
import math
import time
from dataclasses import dataclass, field
from enum import StrEnum
from pathlib import Path

import anthropic
from PIL import Image

from llm.agent import SYSTEM, TOOLS, Trace, _request, _time_left
from llm.merge import Seam, apply_review, clip_polyline_inside
from llm.views import Box, render_view, to_image_block
from postprocess.uvtt import answer_to_uvtt

PIECE_SQUARES = 8.0  # each strip is shown in pieces about this long, so squares get real zoom

REVIEW_SYSTEM = (
    SYSTEM.split("## How to work")[0]
    + """## Your task
Several agents traced this map at the same time, each one part of it, and their answers \\
were joined by fixed rules. You check the joins. You get close-up crops of the strips along \\
the borders between the parts, with the joined answer drawn on them, and a listing of the \\
walls, portals and lights that lie in the strips. Compare each strip with the image and fix \\
what is wrong there: walls broken, doubled, misjoined, bent or missing at a border, and \\
doors, windows or lights that are wrong, missing or reported twice.

Then call submit_corrections with the complete content the strips should have: everything \\
that belongs inside them, including what was already right (copy it from the listing). \\
Anything you leave out of a strip is removed from it; anything you submit outside the strips \\
is ignored. Lines may run past a strip's edge; they are cut there and joined to the lines \\
outside. You can ask for closer crops inside the strips with view_region (overlay=true shows \\
the joined answer, or your submission once you have made one). After a submission you see \\
it drawn over the map and may submit again; the last submission is the result. When it is \\
right, reply with one short sentence saying so."""
)

VIEW_TOOL = {
    **TOOLS[0],
    "description": (
        "Return a zoomed crop of a strip with the labeled grid. Give the window in grid "
        "squares; it is cut to the strip it overlaps most. Set overlay to true to draw the "
        "joined answer (or your latest submission) on the crop."
    ),
}
SUBMIT_TOOL = {
    **TOOLS[1],
    "name": "submit_corrections",
    "description": (
        "Submit the complete content of all the strips (it replaces any earlier submission) "
        "and get it back drawn over the map: walls red, portals magenta, lights yellow. Items "
        "outside the strips are ignored. Arc angles as in the tracer: degrees from east (0) "
        "toward south (90)."
    ),
}
REVIEW_TOOLS = [VIEW_TOOL, SUBMIT_TOOL]


class ReviewState(StrEnum):
    """Where the seam review stands. `done` means a submission exists to apply."""

    not_needed = "not_needed"  # one chunk: no seams
    waiting = "waiting"
    reviewing = "reviewing"
    done = "done"
    failed = "failed"
    skipped = "skipped"  # no time or budget left, or no chunk to review


@dataclass
class ReviewRun:
    """What the seam review did and cost; `trace.answer` is its last submission."""

    state: ReviewState
    model: str = ""
    trace: Trace = field(default_factory=Trace)
    seconds: float = 0.0
    error: BaseException | None = None
    removed: dict = field(default_factory=dict)  # filled in by the orchestrator when applied
    added: dict = field(default_factory=dict)


def strip_pieces(seam: Seam, piece: float = PIECE_SQUARES) -> list[Box]:
    """A seam's strip cut into equal pieces about `piece` squares long, along the seam."""
    x0, y0, x1, y1 = seam.strip
    if seam.axis == "x":
        n = max(1, math.ceil((y1 - y0) / piece))
        return [(x0, y0 + (y1 - y0) * i / n, x1, y0 + (y1 - y0) * (i + 1) / n) for i in range(n)]
    n = max(1, math.ceil((x1 - x0) / piece))
    return [(x0 + (x1 - x0) * i / n, y0, x0 + (x1 - x0) * (i + 1) / n, y1) for i in range(n)]


def _overlap(a: Box, b: Box) -> Box | None:
    """The intersection of two boxes, or None when it has no area."""
    x0, y0 = max(min(a[0], a[2]), b[0]), max(min(a[1], a[3]), b[1])
    x1, y1 = min(max(a[0], a[2]), b[2]), min(max(a[1], a[3]), b[3])
    return (x0, y0, x1, y1) if x0 < x1 and y0 < y1 else None


def _in_strips(box: Box, strips: list[Box]) -> Box | None:
    """`box` cut to the strip it overlaps most, or None when it overlaps none."""
    cuts = [c for s in strips if (c := _overlap(box, s)) is not None]
    return max(cuts, key=lambda c: (c[2] - c[0]) * (c[3] - c[1]), default=None)


def _rounded(value):
    """Numbers in a listing rounded to 0.01 square, so the text stays short."""
    if isinstance(value, float):
        return round(value, 2)
    if isinstance(value, dict):
        return {k: _rounded(v) for k, v in value.items()}
    if isinstance(value, list):
        return [_rounded(v) for v in value]
    return value


def strip_listing(merged: dict, strips: list[Box]) -> dict:
    """The merged walls (their parts inside the strips), portals and lights in the strips."""

    def inside(x: float, y: float) -> bool:
        """Whether a point lies in a strip."""
        return any(s[0] <= x <= s[2] and s[1] <= y <= s[3] for s in strips)

    walls = []
    for w in merged.get("walls", []):
        line = [(p["x"], p["y"]) for p in w["points"]]
        for piece in clip_polyline_inside(line, strips):
            walls.append({"points": [{"x": x, "y": y} for x, y in piece]})
    portals = [
        p
        for p in merged.get("portals", [])
        if inside((p["x1"] + p["x2"]) / 2, (p["y1"] + p["y2"]) / 2)
    ]
    lights = [li for li in merged.get("lights", []) if inside(li["x"], li["y"])]
    return _rounded({"walls": walls, "portals": portals, "lights": lights})


def review_seams(
    image: Image.Image,
    map_size: tuple[int, int],
    merged: dict,
    seam_list: list[Seam],
    cfg: dict,
    client: anthropic.Anthropic,
    deadline: float | None = None,
    views_dir: Path | None = None,
) -> ReviewRun:
    """Run the orchestrator model's review of every seam; never applies the result.

    `cfg` is `llm.orchestrator.load_chunked_config`'s: `cfg["review"]` holds the model and
    the review's limits. Returns `done` with `trace.answer` set when there is a submission
    (also after a later error), `skipped` when the deadline passed before the first request,
    and `failed` otherwise (with the error or the stop reason). Raises only for programming
    errors; API errors end the review.
    """
    start = time.monotonic()
    review = cfg["review"]
    rcfg = {"model": review["model"]}
    prices = cfg["prices"][review["model"]["name"]]
    view_cfg = cfg["views"]
    ppg = image.width / map_size[0]
    strips = [s.strip for s in seam_list]
    run = ReviewRun(state=ReviewState.reviewing, model=review["model"]["name"])
    trace = run.trace
    merged_uvtt = answer_to_uvtt(merged, map_size)
    latest = merged_uvtt  # what overlay=true draws: the joined answer, then the submission
    shots = 0

    def show(box: Box, uvtt: dict | None, with_strips: bool = False) -> tuple[dict, float]:
        """Render a crop with the labeled grid; save a copy if asked; return an image block."""
        nonlocal shots
        view, zoom = render_view(
            image,
            ppg,
            box,
            view_cfg["max_px"],
            view_cfg["max_zoom"],
            uvtt,
            strips=strips if with_strips else None,
        )
        if views_dir is not None:
            views_dir.mkdir(parents=True, exist_ok=True)
            view.save(views_dir / f"{shots:02d}.jpg", quality=view_cfg["jpeg_quality"])
        shots += 1
        return to_image_block(view, view_cfg["jpeg_quality"]), zoom

    def run_tool(name: str, args: dict) -> tuple[list[dict], bool]:
        """Execute one tool call; returns the result content and whether it is an error."""
        nonlocal latest
        if name == "view_region":
            if trace.views >= review["max_views"]:
                return [{"type": "text", "text": "View limit reached. Submit now."}], True
            box = _in_strips((args["x0"], args["y0"], args["x1"], args["y1"]), strips)
            if box is None:
                return [{"type": "text", "text": "That window is outside every strip."}], True
            trace.views += 1
            block, zoom = show(box, latest if args["overlay"] else None)
            left = review["max_views"] - trace.views
            return [
                block,
                {"type": "text", "text": f"{zoom:.0f} px per square. Views left: {left}."},
            ], False
        if name == "submit_corrections":
            if trace.submissions >= review["max_submissions"]:
                text = "Submission limit reached; the previous submission stands. Finish now."
                return [{"type": "text", "text": text}], True
            trace.submissions += 1
            trace.answer = args
            merge_cfg = cfg["chunked"]["merge"]
            final, _, _ = apply_review(
                merged,
                args,
                strips,
                map_size,
                merge_cfg["join_tolerance_squares"],
                merge_cfg["min_piece_squares"],
            )
            latest = answer_to_uvtt(final, map_size)
            block, _ = show((0, 0, *map_size), latest, with_strips=True)
            left = review["max_submissions"] - trace.submissions
            text = f"Recorded. This is the map with your corrections. Submissions left: {left}."
            return [block, {"type": "text", "text": text}], False
        return [{"type": "text", "text": f"Unknown tool {name}."}], True

    left = _time_left(deadline)
    if left is not None and left <= 0:
        run.state, trace.stopped = ReviewState.skipped, "timeout"
        return run

    content: list[dict] = []
    for seam in seam_list:
        for piece in strip_pieces(seam):
            label = (
                f"Seam at {seam.axis} = {seam.at:g}; squares x {piece[0]:g} to {piece[2]:g}, "
                f"y {piece[1]:g} to {piece[3]:g}:"
            )
            content += [{"type": "text", "text": label}, show(piece, merged_uvtt)[0]]
    content.append({"type": "text", "text": json.dumps(strip_listing(merged, strips))})
    spans = "; ".join(
        f"x {s.strip[0]:g} to {s.strip[2]:g}"
        if s.axis == "x"
        else f"y {s.strip[1]:g} to {s.strip[3]:g}"
        for s in seam_list
    )
    intro = (
        f"The map is {map_size[0]} squares wide and {map_size[1]} squares high. The strips "
        f"to check: {spans}, each the map's full length. Above: the strips in pieces, then "
        "the listing of what lies in them now. Check them and submit_corrections."
    )
    content.append({"type": "text", "text": intro})
    messages: list[dict] = [{"role": "user", "content": content}]
    reminded = False
    try:
        while True:
            if trace.turns >= review["max_turns"]:
                trace.stopped = "turn limit"
                break
            if trace.cost_usd >= review["max_cost_usd"]:
                trace.stopped = "cost limit"
                break
            left = _time_left(deadline)
            if left is not None and left <= 0:
                trace.stopped = "timeout"
                break
            response = _request(
                client, rcfg, messages, timeout=left, system=REVIEW_SYSTEM, tools=REVIEW_TOOLS
            )
            trace.turns += 1
            trace.add_usage(response.usage, prices)
            trace.served_by.add(response.model)
            trace.record(response)
            messages.append({"role": "assistant", "content": response.content})
            if response.stop_reason in ("refusal", "max_tokens"):
                trace.stopped = response.stop_reason
                break
            calls = [b for b in response.content if b.type == "tool_use"]
            if not calls:
                if trace.answer is None and not reminded:
                    reminded = True
                    nudge = "You have not called submit_corrections yet. Submit with it."
                    messages.append({"role": "user", "content": nudge})
                    continue
                trace.note = " ".join(b.text for b in response.content if b.type == "text")
                trace.stopped = "done"
                break
            results = []
            for c in calls:
                result, is_error = run_tool(c.name, c.input)
                trace.log.append(
                    {"turn": trace.turns, "tool": c.name, "input": c.input, "error": is_error}
                )
                results.append(
                    {
                        "type": "tool_result",
                        "tool_use_id": c.id,
                        "content": result,
                        "is_error": is_error,
                    }
                )
            messages.append({"role": "user", "content": results})
    except anthropic.APIError as error:
        run.error = error
        trace.stopped = f"{type(error).__name__}"
    run.state = ReviewState.done if trace.answer is not None else ReviewState.failed
    run.seconds = time.monotonic() - start
    return run
