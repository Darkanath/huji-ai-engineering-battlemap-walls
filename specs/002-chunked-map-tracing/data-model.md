# Data Model: Chunked Map Tracing

All positions are in **whole-map grid squares** (origin top-left, y down) unless marked as
image fractions. Existing models in `app/domain.py` (`TraceResult`, `RawAnswer`, `Usage`,
`MapSize`, `PassKind`) and `llm/agent.py` (`Trace`) are reused; this lists what is new or changed.

## Box (existing alias, `llm/views.py`)

`(x0, y0, x1, y1)` in squares, `x0 < x1`, `y0 < y1`.

## AgentChoice (new, `Literal["haiku", "sonnet", "opus"]`)

The selector's value. Default from `[chunked].default_agents` (`"sonnet"`).

## Chunk (new, `llm/merge.py`, frozen dataclass; re-exported by `llm/orchestrator.py`)

| Field | Type | Rule |
| --- | --- | --- |
| `index` | int | 0-based, row by row from the top-left; shown to users as `index + 1` ("part 1") |
| `col`, `row` | int | position in the chunk grid |
| `core` | Box | this chunk's share of the map; the cores of a layout partition the map |
| `window` | Box | `core` grown by the overlap on every side with a neighbour, clipped to the map |

## Layout (function result)

`chunk_layout(map_size, core_squares, overlap_squares, max_per_side) -> list[Chunk]`

- `nx = min(ceil(W / core_squares), max_per_side)`, likewise `ny`; core size `W / nx` by `H / ny`.
- Config validation: `core_squares >= 2`, `0 <= overlap_squares < core_squares / 2`,
  `1 <= max_per_side <= 4` (the spec's cap is 16 chunks).
- Tested: every point lies in exactly one core, from 1 x 1 to 200 x 200; at most 16 chunks.

## Seam (new, `llm/merge.py`, frozen dataclass)

| Field | Type | Rule |
| --- | --- | --- |
| `axis` | `"x"` \| `"y"` | a vertical seam lies at `x = at`, a horizontal one at `y = at` |
| `at` | float | an internal core border (never the map edge) |
| `strip` | Box | the band `strip_squares` either side of the seam, the full map length, clipped to the map |

`seams(layout, map_size, strip_squares) -> list[Seam]`: `(nx - 1) + (ny - 1)` seams; none for one
chunk.

## ChunkState (new, StrEnum, `llm/orchestrator.py`)

`waiting -> tracing -> done | failed`; `waiting -> skipped`. `done`, `failed`, `skipped` are
final.

| State | Meaning |
| --- | --- |
| `waiting` | not started yet |
| `tracing` | its agent is running |
| `done` | ended with an answer (including "kept last submission" after an error) |
| `failed` | ended with no answer; has a failure (an exception or a stop reason) |
| `skipped` | never started: the pass's deadline or cost limit was used up |

## ReviewState (new, StrEnum, `llm/review.py`)

`not_needed` (one chunk) · `waiting -> reviewing -> done | failed`; `waiting -> skipped` (no
time or budget left, or no chunk `done`). `done` means a submission was applied.

## ChunkRun (new, `llm/orchestrator.py`, dataclass)

| Field | Type | Notes |
| --- | --- | --- |
| `chunk` | Chunk | |
| `state` | ChunkState | |
| `trace` | Trace | the agent's own: answer, turns, views, submissions, tokens, cost, stopped, log, responses |
| `seconds` | float | wall-clock time of this agent |
| `error` | BaseException \| None | what ended it, if anything; the app classifies it |

Derived for the agent table: `counts()` → walls (polylines + arcs), portals, lights in
`trace.answer`, before merging; zeros when there is no answer.

## MergeReport (new, `llm/merge.py`, dataclass)

| Field | Type |
| --- | --- |
| `walls_in` / `walls_out` | int: polylines before clipping / after joining |
| `pieces_dropped` | int |
| `ends_snapped` / `joins` | int |
| `portals_kept`, `portals_dropped` | list[int], per chunk index |
| `lights_kept`, `lights_dropped` | list[int], per chunk index |

## ReviewRun (new, `llm/review.py`, dataclass)

| Field | Type | Notes |
| --- | --- | --- |
| `state` | ReviewState | |
| `model` | str | the orchestrator model id |
| `trace` | Trace | turns, views, submissions, tokens, cost, stopped, responses; `answer` = last submission |
| `seconds` | float | |
| `error` | BaseException \| None | |
| `removed`, `added` | dict[str, int] | walls / portals / lights removed from and added to the strips; empty if not applied |

## ChunkedTrace (new, `llm/orchestrator.py`, dataclass): the orchestrator's result

| Field | Type | Notes |
| --- | --- | --- |
| `layout` | list[Chunk] | |
| `seams` | list[Seam] | |
| `runs` | list[ChunkRun] | one per chunk, in index order |
| `merged` | dict \| None | the rule-merged answer (`RawAnswer` form: `walls`, `portals`, `lights`, no `arcs`); None when no chunk is `done` |
| `merge` | MergeReport \| None | |
| `review` | ReviewRun | `not_needed` for one chunk |
| `answer` | dict \| None | final: `merged` with the review applied, or `merged` when the review did not apply |
| `cost_usd`, `seconds` | float | sums over chunks and review (the app adds the size step) |

Derived: `done`, `failed`, `skipped` runs; `untraced` (cores of runs not `done`).

## ChunkBoard (new, `app/progress.py`): live state for the page

Thread-safe (one lock). Holds the layout, the seams, each chunk's `ChunkState` and the
`ReviewState`. `update_chunk(index, state)` and `update_review(state)` from the orchestrator's
callback (worker threads); `snapshot()`, `done_count()`, `total` for the page (main thread).
Lives on the `Session` while a chunked pass runs; when the size step changes the map size, the
board is rebuilt for the new layout before any agent starts.

## Changed: PassKind (`app/domain.py`)

Adds `chunked = "chunked"`. `Settings.profiles` keeps the keys `quick` and `deep`.

## Changed: TraceResult (`app/domain.py`)

New optional fields, empty or None for the two single-session passes:

| Field | Type | Notes |
| --- | --- | --- |
| `agents` | AgentChoice \| None | |
| `orchestrator_model` | str \| None | |
| `chunks` | list[ChunkReport] | one per chunk |
| `review` | ReviewReport \| None | |
| `untraced` | list[tuple[Point, Point]] | top-left and bottom-right of each untraced core, as image fractions |

`ChunkReport` (Pydantic): `part` (index + 1), `state`, `failure` (FailureKind \| None, or
`"limit"` for skipped), `seconds`, `cost_usd`, `views`, `walls`, `portals`, `lights`.

`ReviewReport` (Pydantic): `state`, `failure`, `model_label`, `seconds`, `cost_usd`, `removed`,
`added`.

`usage` and `cost_usd` are sums over the size step, all chunks and the review. `model_id` is the
agents' model.

## Changed: Settings (`app/config.py`)

New `chunked: ChunkedSettings`:

| Field | Type | Rule |
| --- | --- | --- |
| `default_agents` | AgentChoice | |
| `core_squares` | float | >= 2 |
| `overlap_squares` | float | >= 0, < core_squares / 2 |
| `max_per_side` | int | 1..4 |
| `max_parallel` | int | >= 1 |
| `agents` | dict[AgentChoice, AgentSettings] | all three present |
| `limits` | Limits | per chunk agent |
| `review` | ReviewSettings | `strip_squares` > 0; `max_turns`, `max_views`, `max_submissions`, `max_cost_usd`; `expected_seconds`, `expected_cost_usd` (dicts keyed by orchestrator choice) |
| `merge` | MergeSettings | `join_tolerance_squares` > 0, `min_piece_squares` >= 0 |

`AgentSettings`: `name`, `label`, `effort`, `max_tokens`, `fallbacks`, `orchestrator`
(`"sonnet"` \| `"opus"`, must name an entry in `agents`), `deadline_s`, `max_cost_usd`,
`expected_seconds_per_chunk`, `expected_cost_per_chunk_usd`, `estimate` (bool: true until
measured; the button then says "estimate").

Validated: every model named has a price in `[prices]`; the orchestrator entries exist.

Methods: `layout(map_size)`, `expected_max(agents, detect) -> (seconds, cost)` (the same
formula for a `max_per_side` x `max_per_side` layout: the most a pass can take and cost, shown
when detection may change the chunk count; FR-011), and
`expected(map_size, agents, detect) -> (seconds, cost)`:
`seconds = ceil(n / max_parallel) * per_chunk_s + review_s (n > 1) + size_step_s (detect)`;
`cost = n * per_chunk_usd + review_usd (n > 1) + size_step_usd (detect)`.

`SizeStep` gains `expected_seconds` (default 8) for this sum.

## Changed: Session (`app/service.py`)

Adds `agents: AgentChoice` (from config, changed by the selector) and `board: ChunkBoard | None`
(set by `begin_pass` for a chunked pass, cleared by `finish_pass`).
