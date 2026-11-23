# Contract: Tracer, Merge, Review and Orchestrator (`llm/`)

## `llm/agent.py` (changed)

```python
def trace_map(image, map_size, cfg=None, client=None, views_dir=None, deadline=None,
              trace=None, window: Box | None = None, core: Box | None = None) -> Trace
```

- `window=None`: unchanged; the first request is identical to today's (tested against a
  recorded request).
- With `window` (and its `core`, which defaults to `window`): system prompt `CHUNK_SYSTEM`;
  opening message = overview of the whole map with `window` outlined, `window` at full zoom
  (at no less than the image's own pixels per square, or the view cap if lower; FR-002), intro
  naming window and core; `view_region` clamped
  to `window`; the overlay after `submit_answer` shows `window`. Answers in whole-map squares.
- Raises only for API errors, as today.

`CHUNK_SYSTEM` shares the coordinate and labeling text with `SYSTEM` (same constants) and is the
same for every chunk; the core goes in the intro text, so the system prompt can be cached.

## `llm/views.py` (changed)

`render_view(..., outline: Box | None = None, strips: list[Box] | None = None)`: draws `outline`
as a thick rectangle and `strips` as translucent bands. Defaults keep every existing image
identical.

## `llm/merge.py` (new, pure)

The layout geometry lives here too (`Chunk`, `chunk_layout`), because `merge.py` needs the
`Chunk` type and `orchestrator.py` imports `merge.py`; `llm.orchestrator` re-exports both, so
the import path in the orchestrator section below still works. `llm/merge.py` imports nothing
from the other new modules.

```python
def chunk_layout(map_size, core_squares, overlap_squares, max_per_side) -> list[Chunk]
def clip_polyline(points, box: Box) -> list[list[tuple[float, float]]]        # inside box
def clip_polyline_outside(points, boxes: list[Box]) -> list[list[tuple[float, float]]]
def owner(x: float, y: float, layout: list[Chunk]) -> int
def seams(layout: list[Chunk], map_size, strip_squares: float) -> list[Seam]
def merge_answers(layout, answers: dict[int, dict], map_size,
                  join_tolerance: float, min_piece: float) -> tuple[dict, MergeReport]
def apply_review(merged: dict, submission: dict, strips: list[Box], map_size,
                 join_tolerance: float, min_piece: float) -> tuple[dict, dict, dict]
    # -> (final answer, removed counts, added counts)
def seam_checks(answer: dict, seams: list[Seam], gap: float = 0.1,
                same: float = 0.5) -> dict[str, int]
    # -> {"seam_gap_ends", "duplicate_portals", "duplicate_lights"}
```

`seam_checks` measures SC-003 on any answer: `seam_gap_ends` counts wall ends lying on a seam
(within 1e-6) with no other wall point within `gap` squares; `duplicate_portals` and
`duplicate_lights` count pairs whose midpoints or positions are within `same` squares.

Guarantees, each tested:

- same input, same output; no output point outside the map;
- every portal and light in a merge comes from the chunk that owns it;
- a wall crossing a seam with ends within tolerance comes out as one polyline; a seam end with
  no partner is not moved beyond the tolerance and never extended;
- one chunk: the merge returns its answer (arcs as polylines, clipped to the map);
- `apply_review` changes nothing outside the strips: every wall point, portal and light of
  `merged` outside the strips' union is in the result, and nothing from `submission` outside
  the strips is;
- cutting a label file's own walls, portals and lights into chunks and merging them loses
  nothing (wall boundary F1 >= 0.99 and portal recall 1.0 against the label; quickstart step 2).

## `llm/review.py` (new)

```python
def review_seams(image, map_size, merged: dict, seams: list[Seam], cfg: dict, client,
                 deadline: float | None = None, views_dir: Path | None = None) -> ReviewRun
```

- `cfg["review"]` holds the orchestrator's model and limits ([config contract](config-and-cli.md)).
- Opening message: `REVIEW_SYSTEM`; per seam, crops along its strip in pieces of about 8
  squares with `merged` drawn on them; a JSON listing of the merged items touching the strips.
- Tools: `view_region` (clamped to the strips' union) and `submit_corrections` (strict schema,
  same item shapes as `submit_answer`). After each submission the corrected strips are shown.
- Returns `ReviewRun` with `state = done` and `trace.answer` set when a submission exists (also
  after a later error), else `failed` (with the error or stop reason) or `skipped` (deadline
  passed before the first request). Raises only for programming errors.
- Does not apply the submission; the orchestrator calls `apply_review`.

## `llm/orchestrator.py` (new)

```python
from llm.merge import Chunk, chunk_layout   # re-exported
def load_chunked_config(agents: str, path: Path = CONFIG) -> dict
def trace_chunks(image, map_size, cfg: dict, client, deadline: float | None = None,
                 on_update: Callable[[str, int | None, str], None] | None = None,
                 out_dir: Path | None = None) -> ChunkedTrace
```

- Runs up to `max_parallel` agents at once (one `trace_map(window=...)` each), sharing `client`
  and `deadline`.
- Before starting a chunk: deadline passed, or summed cost of all chunks so far >= the choice's
  `max_cost_usd` → `skipped`.
- An agent that raises: `done` if its trace has an answer, else `failed` with `error` kept;
  `refusal` / `max_tokens` with no answer → `failed`.
- Merges the `done` answers (`merge_answers`); if there is more than one chunk and at least one
  is `done`, and time and budget are left, runs `review_seams` and then `apply_review` on its
  submission; otherwise the review is `skipped` (or `not_needed` for one chunk).
- `on_update(kind, index, state)` with `kind` `"chunk"` or `"review"`; called from worker
  threads; must be quick; errors from it are caught and ignored.
- Never raises for a chunk or review failure.
- With `out_dir`, writes views under `out_dir/chunks/<i>/views/` and `out_dir/review/views/`.
