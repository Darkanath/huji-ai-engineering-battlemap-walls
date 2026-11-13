# Data Model: Battlemap Tracer App

Phase 1 of the plan. Pydantic v2 models unless noted. Nothing here is stored beyond the
session, except evaluation runs under `runs/`.

## Coordinates

Three systems; each value lives in exactly one.

| System | Used by | Definition |
| --- | --- | --- |
| Image fractions | Everything the app stores (`TraceResult`) | `fx`, `fy` in 0..1 of the image width and height, origin top-left, y down |
| Grid squares | The model's answer; the export file; label files | Decimal squares, origin top-left, y down |
| Pixels | Drawing the preview; resizing the image | Image pixels |

Conversions (in `app/domain.py`, tested):

- **Answer -> fractions**, with the map size the trace used and `ppg = image_width / map_width`
  (the value the views were drawn with, on both axes):
  `fx = x / map_width`, `fy = y * ppg / image_height`.
- **Fractions -> grid squares**, with the map size on screen:
  `x = fx * map_width`, `y = fy * map_height`.
- **Fractions -> pixels**: `px = fx * image_width`, `py = fy * image_height`.

Values slightly outside 0..1 are clamped (a wall end traced a hair past the border).

## Domain models (`app/domain.py`)

**Point**: `fx: float`, `fy: float` (each 0..1 after clamping).

**Wall**: `points: list[Point]`, at least 2. Straight walls and curves alike; arcs from the
model's answer arrive here already turned into polylines.

**Portal**: `a: Point`, `b: Point`, the two ends of a door or window. One type for both.
`a` and `b` must differ.

**LightTier**: `small | medium | large`.

**Light**: `at: Point`, `tier: LightTier`. The tier never changes when the map size changes.

**MapSize**: `width: int`, `height: int`, each 1..200.

**MapSizeSource**: `default | typed | detected | not_found`.
- `default`: the pre-filled 25 x 25, untouched.
- `typed`: the user entered it. Wins over everything.
- `detected`: the model worked it out during a pass.
- `not_found`: detection ran and found no grid; the size in the fields was used.

**PassKind**: `quick | deep`.

**Usage**: `input_tokens`, `output_tokens`, `cache_write_tokens`, `cache_read_tokens`
(ints), `turns`, `views`, `submissions` (ints).

**TraceResult**:

| Field | Type | Notes |
| --- | --- | --- |
| `walls` | `list[Wall]` | May be empty |
| `portals` | `list[Portal]` | May be empty |
| `lights` | `list[Light]` | May be empty |
| `note` | `str` | The model's closing remark on what it was unsure of |
| `kind` | `PassKind` | Which pass produced it |
| `model_id` | `str` | The model that was asked |
| `served_by` | `list[str]` | Models that answered (a fallback shows here) |
| `effort` | `str` | Effort level used |
| `elapsed_s` | `float` | Whole pass, including the map-size turn |
| `usage` | `Usage` | Whole pass |
| `cost_usd` | `float` | Estimate from `usage` and the price table |
| `traced_size` | `MapSize` | The size the trace used |
| `size_source` | `MapSizeSource` | `detected`, `not_found`, or what the user had |

An empty mask (no walls, portals or lights) is a valid `TraceResult`, not a failure. The UI
says nothing was found.

## Failures (`app/errors.py`)

**FailureKind**: `refusal | output_limit | pass_limit | rate_limit | provider_busy |
auth | missing_key | network | timeout | unreadable | unexpected`.

**PassFailure**: `kind: FailureKind`, `kind_of_pass: PassKind`, `elapsed_s: float`,
`usage: Usage | None`, `cost_usd: float | None`, `detail: str` (for the log only; never
shown). `message(kind)` returns the user-facing text; the table is in
[contracts/ui.md](contracts/ui.md).

**UploadRejected**: `reason: wrong_type | too_large | not_an_image`, with its message.
Raised before any model call.

**MapSizeInvalid**: the range message. Raised before any model call.

## Session state (`app/service.py`)

One `Session` per browser session, held in `gr.State`. A plain mutable object.

| Field | Type | Notes |
| --- | --- | --- |
| `token` | `str` | New on every upload. A pass result is applied only if it matches |
| `image` | `PIL.Image` or `None` | The upload, RGB |
| `image_name` | `str` | Base name for the download |
| `map_size` | `MapSize` | What the fields show |
| `size_source` | `MapSizeSource` | |
| `detect_size` | `bool` | The option; on for a new upload, off once the user types or a size is detected |
| `result` | `TraceResult` or `None` | The mask on screen |
| `last_failure` | `PassFailure` or `None` | For the message area |
| `running` | `PassKind` or `None` | A pass in flight |
| `started_at` | `float` or `None` | For the elapsed time |
| `extension` | `.dd2vtt | .uvtt` | The download choice |
| `tmp_dir` | `Path` | Per session; removed when the session ends |

### State transitions

```text
EMPTY --upload ok--> READY --suggest--> RUNNING(quick) --ok--> MASK
                       ^                      |                  |
                       |                      +--fail--> READY (message)
                       |                                         |
                       |      MASK --deeper--> RUNNING(deep) --ok--> MASK (replaced)
                       |                            |
                       |                            +--fail--> MASK (earlier mask kept, message)
                       |
any state --upload ok--> READY (token replaced; a running pass's result is dropped)
any state --upload rejected--> unchanged (message)
MASK --map size typed--> MASK (preview and export rebuilt; no pass)
MASK --accept--> MASK (file downloaded)
```

Rules:

- `Suggest walls` is enabled in READY and MASK when nothing is running.
- `Deeper examination` is enabled only in MASK when nothing is running.
- `Accept mask` is enabled whenever `result` is not `None`, including while a pass runs.
- A failed pass never clears `result`.
- When a pass finishes with `size_source = detected`, `map_size` is set to the detected
  size and `detect_size` turns off. With `not_found`, `map_size` is left as it was.
- If the user changes the map size while a pass runs, the finished result is shown on the
  size on screen (fractions make this automatic); a detected size does not overwrite a
  size the user typed during the pass.

## Settings (`app/config.py`)

Validated from `llm/configs/claude.toml`; shape in
[contracts/config-and-cli.md](contracts/config-and-cli.md).

- **Profile**: `name` (model id), `label` (for the status line, e.g. "Sonnet 5.5"),
  `effort`, `max_tokens`, `fallbacks: bool`, `deadline_s`, `expected_seconds`,
  `expected_cost_usd`.
- **Limits**: `max_turns`, `max_views`, `max_submissions`, `max_cost_usd` (as today).
- **Views**: `max_px`, `max_zoom`, `jpeg_quality`, `quadrants` (as today).
- **Prices**: per model id, `input` and `output` USD per million tokens.
- **LightSpec** per tier: `range` (squares), `intensity`.
- **AppLimits**: `max_upload_mb = 20`, `min_squares = 1`, `max_squares = 200`,
  `default_width = 25`, `default_height = 25`, `export_ppg = 70`, `export_jpeg_quality = 90`.

Validation: every profile's model id must have a price entry; the three light tiers must
all be present; `deadline_s > 0`.

## The model's answer (boundary, in `llm/agent.py`)

Unchanged tool schema, in grid squares: `walls[].points[]{x,y}`,
`arcs[]{cx,cy,r,start_deg,end_deg}`, `portals[]{x1,y1,x2,y2}`,
`lights[]{x,y,tier}`. New tool for the map-size turn:
`report_map_size {grid_found: bool, width: int, height: int}`.

`app/tracer.py` validates the last submission into a `RawAnswer` model, turns arcs into
polylines (`postprocess.uvtt.arc_points`), drops walls with fewer than 2 points, converts
to fractions, and builds the `TraceResult`. A submission that fails validation gives
`FailureKind.unreadable`.

## Export file

See [contracts/export-file.md](contracts/export-file.md). Built from `TraceResult`, the
`MapSize` on screen, the image and the lights table.

## Evaluation records (`runs/<run>/`)

Per map: `responses.json` (raw model responses: text and tool calls), `trace.json`,
`answer.json`, `<map>.dd2vtt`, `preview.jpg`, `views/`. Per run: `summary.csv` with one row
per map: map, profile, model, effort, stopped, turns, views, submissions, cost, seconds,
wall IoU, wall boundary F1, portal IoU, portal recall, light IoU, true size, detected size,
size right.
