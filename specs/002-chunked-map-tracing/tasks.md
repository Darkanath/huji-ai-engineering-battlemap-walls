---
description: "Tasks for Chunked Map Tracing"
---

# Tasks: Chunked Map Tracing

**Input**: Design documents from `specs/002-chunked-map-tracing/`

**Prerequisites**: [plan.md](plan.md), [spec.md](spec.md), [research.md](research.md),
[data-model.md](data-model.md), [contracts/](contracts/), [quickstart.md](quickstart.md)

**Tests**: required. Spec FR-015 asks for tests of layout, merge and orchestrator with the fake
client, and constitution IV asks for a test of every module that transforms data and of every
model-call failure. Within each story, write the test task first and see it fail, then
implement.

**Organization**: tasks are grouped by user story (US1 P1, US2 P2, US3 P3) so each can be built
and checked on its own.

**Conventions for every task** (CLAUDE.md, constitution IV): docstrings on every module,
function, test, fixture and nested helper; type hints on public functions; `ruff` clean; no
test makes a paid call; run everything through Docker Compose
(`docker compose run --rm app pytest …`). Tasks marked **(owner)** are the project owner's to do
or approve (paid calls, Roll20).

## Format: `[ID] [P?] [Story] Description`

- **[P]**: can run in parallel (different files, no dependency on an unfinished task)
- **[Story]**: US1, US2, US3 from spec.md

## Path Conventions

The existing layout (plan.md, Structure Decision): `llm/`, `app/`, `tests/`, `docs/` at the
repo root. No `src/`.

---

## Phase 1: Setup

**Purpose**: the config the whole feature reads, and a guard that keeps the single-session
tracer unchanged.

- [X] T001 Add the chunked tables to `llm/configs/claude.toml` exactly as in `contracts/config-and-cli.md`: `[chunked]` (`default_agents = "sonnet"`, `core_squares = 13`, `overlap_squares = 1`, `max_per_side = 4`, `max_parallel = 4`), `[chunked.agents.haiku]`, `[chunked.agents.sonnet]`, `[chunked.agents.opus]` (with `orchestrator`, `deadline_s`, `max_cost_usd`, `expected_seconds_per_chunk`, `expected_cost_per_chunk_usd`, `estimate = true`, and the ESTIMATE comments), `[chunked.limits]`, `[chunked.review]` (with the inline tables `expected_seconds = { sonnet = 20, opus = 45 }` and `expected_cost_usd = { sonnet = 0.05, opus = 0.15 }`), `[chunked.merge]`; add `expected_seconds = 8` to `[size_step]`. Check that the existing tests still pass (`app/config.py` must ignore the new tables until T026).
- [X] T002 Record the single-session guard **before any change to `llm/agent.py`**: in `tests/test_llm_agent.py` add `test_single_session_first_request_is_unchanged`, which runs `trace_map` on the demo map (`tests/conftest.py: DEMO_MAP`, image decoded with `data.rasterize.decode_image`) with a `FakeClient` that submits once, and compares the first request's `system`, `tools`, the text blocks of the first message, and the number and pixel size of its images with a new fixture `tests/fixtures/request_single_session.json`, written by a one-off run of the test's helper and committed with it (describe in `tests/fixtures/README.md` how to regenerate it).

---

## Phase 2: Foundational

**Purpose**: pieces every story builds on: the config loader for the tool loops and the extra
drawing in `render_view`.

**⚠️ No user story work starts before this phase is done.**

- [X] T003 [P] In `tests/test_llm_views.py`, test `render_view(..., outline=None, strips=None)` returns the same image bytes as before for the same inputs; with `outline=(2, 2, 8, 8)` pixels on that rectangle's border change and pixels well inside it do not; with `strips=[(11.5, 0, 13.5, 25)]` pixels inside the band are tinted and pixels outside are not.
- [X] T004 In `llm/views.py`, add the optional `outline: Box | None = None` (a thick rectangle, a color not used for walls, portals or lights) and `strips: list[Box] | None = None` (translucent amber bands) arguments to `render_view`, drawn in the view's whole-map squares; the defaults keep every existing image identical (T003).
- [X] T005 [P] In a new `tests/test_llm_orchestrator.py`, test `load_chunked_config(agents)`: for `"sonnet"` `cfg["model"]["name"] == "claude-sonnet-5-5"`, `cfg["limits"]` equals `[chunked.limits]`, `cfg["review"]["model"]["name"] == "claude-sonnet-5-5"` and `cfg["review"]` holds `[chunked.review]`'s limits; for `"haiku"` the review model is Sonnet's; for `"opus"` both are Opus; `cfg["chunked"]` holds the `[chunked]` table and the choice's `deadline_s` and `max_cost_usd`; `cfg["prices"]` and `cfg["views"]` are present; an unknown choice raises `ValueError`.
- [X] T006 Create `llm/orchestrator.py` with its module docstring and `load_chunked_config(agents: str, path: Path = CONFIG) -> dict` (T005): reads the TOML, builds `cfg["model"]` from `[chunked.agents.<agents>]` (`name`, `label`, `effort`, `max_tokens`, `fallbacks`), replaces `cfg["limits"]` with `[chunked.limits]`, builds `cfg["review"] = {"model": <the orchestrator entry's model fields>, **[chunked.review]}`, and copies the choice's `orchestrator`, `deadline_s`, `max_cost_usd` into `cfg["chunked"]`.

**Checkpoint**: views and config loader ready.

---

## Phase 3: User Story 1 - Trace a map in chunks and get one file (Priority: P1) 🎯 MVP

**Goal**: split a map into chunks, trace each with its own agent at the same time, merge by
fixed rules, have the orchestrator model review the seams, and get one valid Universal VTT
file.

**Independent test**: with fake clients only, a four-chunk run on the demo map gives one file
that loads with `data.rasterize.load_uvtt`; a wall crossing a seam is one continuous wall; a door
and a light in an overlap appear once; the review changes only the seam strips.

### Layout and clipping (`llm/merge.py`)

- [X] T007 [P] [US1] In a new `tests/test_llm_merge.py`, test `chunk_layout(map_size, core_squares=13, overlap_squares=1, max_per_side=4)`: for 1x1, 13x13, 25x25, 27x14, 50x50 and 200x200, random points (seeded) each lie in exactly one core ("half-open on the right and bottom, closed at the map edge"); "nx = min(ceil(W / core_squares), max_per_side)" and likewise ny, so never more than 16 chunks; 25x25 gives 2x2 cores of 12.5; 13x13 gives one chunk with `core == window == (0, 0, 13, 13)`; every window contains its core, reaches 1 square past every inner border, and is clipped to the map; `index` runs row by row from the top-left.
- [X] T008 [US1] Create `llm/merge.py` (module docstring: rule-based merge, no model call) with the frozen dataclass `Chunk(index, col, row, core: Box, window: Box)`, `chunk_layout(map_size, core_squares, overlap_squares, max_per_side) -> list[Chunk]` and `owner(x, y, layout) -> int` (the chunk whose core holds the point, half-open intervals, closed at the map edge) (T007). Re-export `Chunk` and `chunk_layout` from `llm/orchestrator.py`.
- [X] T009 [P] [US1] In `tests/test_llm_merge.py`, test `clip_polyline(points, box)`: a segment fully inside is kept; one crossing an edge is cut exactly on it; one leaving and re-entering gives two pieces; a segment on the box edge is kept once; a polyline fully outside gives nothing. Test `clip_polyline_outside(points, boxes)`: the complement of the union of overlapping boxes, with pieces cut exactly on the box edges.
- [X] T010 [US1] In `llm/merge.py`, implement `clip_polyline` (Liang-Barsky per segment, joining consecutive inside segments into one piece) and `clip_polyline_outside` (per segment, the union of the inside parameter intervals of all boxes, then its complement) (T009).

### Rule-based merge

- [X] T011 [US1] In `tests/test_llm_merge.py`, test `merge_answers(layout, answers, map_size, join_tolerance=0.3, min_piece=0.05)` on a 2x2 layout of 25x25: a horizontal wall traced by both left chunks across x = 12.5 (ends 0.2 square apart at the seam) comes out as one polyline; four walls meeting at (12.5, 12.5) share one point and are not concatenated; a door whose midpoint is in chunk 0's core, reported by chunks 0 and 1, comes out once, and `MergeReport.portals_dropped[1] == 1`; a light likewise; a wall ending on a seam with no partner within 0.3 is not moved by more than 0.3 and never extended; a clipped piece shorter than 0.05 is dropped and counted in `pieces_dropped`; an arc spanning a seam joins like a polyline; the output has `walls`, `portals`, `lights` and no `arcs`; no output point is outside the map; calling twice with the same input gives the same output; with a one-chunk layout the output equals the input answer with arcs as polylines.
- [X] T012 [US1] In `llm/merge.py`, implement `MergeReport` (fields as in data-model.md: `walls_in`, `walls_out`, `pieces_dropped`, `ends_snapped`, `joins`, `portals_kept`, `portals_dropped`, `lights_kept`, `lights_dropped`, the last four "list[int], per chunk index") and `merge_answers`: arcs to polylines with `postprocess.uvtt.arc_points`; clip each chunk's walls to its core; keep portals by midpoint owner and lights by position owner; group seam ends (within 1e-6 of an inner core border) closer than `join_tolerance` and move each group to its mean; concatenate two polylines where exactly two ends share a point (T011).
- [X] T013 [US1] In `tests/test_llm_merge.py`, add the label-cut test (quickstart step 2): read the demo map's `.dd2vtt` (`DEMO_MAP`), turn it into answer form (a helper in the test: `line_of_sight` and `objects_line_of_sight` to `walls`, portal `bounds` to `x1, y1, x2, y2`, light `range` to its tier with `data.rasterize.LIGHT_TIERS`), give each chunk of a 2x2 layout the part of it that lies in its window, merge, rasterize both with `data.rasterize.rasterize_mask` at 32 px per square and score with `eval.metrics`: wall boundary F1 >= 0.99 and `portal_recall == 1.0` (SC-003).

### Agents on a window (`llm/agent.py`)

- [X] T014 [US1] In `tests/test_llm_agent.py`, test `trace_map(..., window=(0, 0, 13.5, 13.5))` with a `FakeClient`: the request's `system` is `CHUNK_SYSTEM`; the first message holds exactly two images (the overview with the window outlined, then the window) and an intro text naming the window and the core; a `view_region` call reaching outside the window is clamped to it; the overlay after `submit_answer` is rendered for the window; the answer stays in whole-map squares; the window's first view is at no less than the image's own pixels per square, or at the view cap (`max_px`) when the window is too large for that (FR-002; check a 25x25 map at 70 px per square and a 200x200 map's 50-square window). T002's guard must still pass.
- [X] T015 [US1] In `llm/agent.py`, split `SYSTEM` into shared constants (role, coordinates, what to mark, the grid hint) plus a "How to work" part, keeping `SYSTEM`'s text byte for byte; add `CHUNK_SYSTEM` (same shared parts; a "How to work" for one part of a larger map: whole-map coordinates, trace everything inside the window up to its edge including the margin a neighbour also traces, nothing outside); add `window: Box | None = None` to `trace_map`: with a window, open with the overview (`render_view(..., outline=window)`), the window view, and the intro naming window and core (core passed as a keyword, e.g. `core: Box | None = None`); clamp `view_region` boxes to the window; render the post-submit overlay for the window (T014, T002).

### Seam review (`llm/merge.py`, `llm/review.py`)

- [X] T016 [P] [US1] In `tests/test_llm_merge.py`, test `seams(layout, map_size, strip_squares=1.0)`: a 2x2 layout of 25x25 gives 2 seams (x = 12.5 and y = 12.5) with strips `(11.5, 0, 13.5, 25)` and `(0, 11.5, 25, 13.5)`; a 3x2 layout gives 3; one chunk gives none; strips are clipped to the map.
- [X] T017 [US1] In `llm/merge.py`, add the frozen dataclass `Seam(axis: "x" | "y", at: float, strip: Box)` and `seams(layout, map_size, strip_squares)`, "(nx - 1) + (ny - 1) seams; none for one chunk" (T016).
- [X] T018 [US1] In `tests/test_llm_merge.py`, test `apply_review(merged, submission, strips, map_size, join_tolerance, min_piece)`: every wall point, portal and light of `merged` outside the strips' union is in the result; nothing of `submission` outside the strips is; a submitted wall across a strip is joined to the merged walls at the strip edges; an empty submission removes the strips' content and nothing else; the removed and added counts (`walls`, `portals`, `lights`) are right. Also test `seam_checks(answer, seams, gap=0.1, same=0.5)`: a wall end on a seam with no other wall point within 0.1 square counts one `seam_gap_ends`; two walls meeting there count none; two portals with midpoints 0.3 apart count one `duplicate_portals`; likewise `duplicate_lights`.
- [X] T019 [US1] In `llm/merge.py`, implement `apply_review` -> `(final answer, removed counts, added counts)`: merged walls clipped with `clip_polyline_outside(strips)`, merged portals and lights inside a strip removed by position, submission walls clipped to each strip with `clip_polyline` (arcs converted first), submission portals and lights kept only inside a strip, then snap and join ends on the strip edges with the same rule as `merge_answers`; and `seam_checks` as defined in contracts/orchestrator.md (T018).
- [X] T020 [P] [US1] In a new `tests/test_llm_review.py`, test `review_seams(image, map_size, merged, seams, cfg, client, deadline)` with a `FakeClient`: the request uses `REVIEW_SYSTEM` and the orchestrator model from `cfg["review"]["model"]`; the first message holds, per strip, crops of about 8 squares along it with `merged` drawn on them, and a JSON listing of the merged items touching the strips; the tools are `view_region` (clamped to the strips' union) and `submit_corrections`; a submission gives `state == done` and `trace.answer`; `refusal` or `max_tokens` with no submission gives `failed`; a deadline already passed gives `skipped` with no request; an API error after a submission gives `done`; an API error before any gives `failed` with `error` kept; turn, view and submission limits from `cfg["review"]` stop the loop.
- [X] T021 [US1] Create `llm/review.py` (module docstring): `ReviewState` StrEnum (`not_needed`, `waiting`, `reviewing`, `done`, `failed`, `skipped`), the dataclass `ReviewRun(state, model, trace, seconds, error, removed, added)`, `REVIEW_SYSTEM`, the strict `submit_corrections` tool (same item shapes as `submit_answer`), and `review_seams` reusing `llm.agent._request`, `Trace`, `render_view(..., strips=...)` and `postprocess.uvtt.answer_to_uvtt`; it does not apply the submission (T020).

### Orchestrator (`llm/orchestrator.py`)

- [X] T022 [US1] In `tests/conftest.py`, add a `RoutingFake` client next to `FakeClient` (docstring; a lock; picks each agent's script by the window named in the intro text of its first request, and the reviewer's script by `REVIEW_SYSTEM`; `FakeClient` itself is not changed). In `tests/test_llm_orchestrator.py`, test `trace_chunks(image, map_size, cfg, client, deadline, on_update, out_dir)` on the demo map: four scripted agents plus a reviewer give `ChunkedTrace` with four `done` runs, `merged`, `merge`, `review.state == done` and `answer` = merged with the review applied; with `max_parallel = 1` agents start in index order; a deadline already passed makes every chunk `skipped` and sends nothing; a cost limit reached after the first chunk (`max_parallel = 1`) skips the rest; one agent raising `anthropic.APITimeoutError`, `APIConnectionError`, `RateLimitError`, `AuthenticationError`, a 5xx `APIStatusError`, or stopping with `refusal` / `max_tokens` and no answer is `failed` with the others `done`; an agent raising after a submission is `done`; no `done` chunk means `merged is None`, `answer is None` and `review.state == skipped`; a one-chunk map gives `review.state == not_needed`; `on_update` receives `("chunk", i, state)` and `("review", None, state)` in a valid order, and an exception inside it is ignored; with `out_dir`, `chunks/<i>/views/` and `review/views/` are written.
- [X] T023 [US1] In `llm/orchestrator.py`, implement `ChunkState` (`waiting`, `tracing`, `done`, `failed`, `skipped`; "`done`, `failed`, `skipped` are final"), `ChunkRun(chunk, state, trace, seconds, error)` with `counts()` (walls = polylines + arcs, portals, lights of `trace.answer`; zeros without one), `ChunkedTrace(layout, seams, runs, merged, merge, review, answer, cost_usd, seconds)` with `done`, `failed`, `skipped` and `untraced`, and `trace_chunks`: a `ThreadPoolExecutor(max_workers=max_parallel)`, one `trace_map(window=..., core=...)` per chunk sharing `client` and `deadline`; before each start, skip on deadline or when the summed live cost >= the choice's `max_cost_usd`; classify each end as in contracts/orchestrator.md; merge the `done` answers; run `review_seams` and `apply_review` when there is more than one chunk, at least one `done`, and time and budget left, else mark the review `skipped` or `not_needed`; call `on_update` inside `try/except` (T022).
- [X] T024 [US1] In `tests/test_llm_orchestrator.py`, add the end-to-end test (US1 acceptance 1-3): a `RoutingFake` four-chunk run on the demo map, `postprocess.uvtt.answer_to_uvtt` + `write_uvtt` to a temp file, `data.rasterize.load_uvtt` loads it, one continuous wall across x = 12.5, one door and one light in the overlap.

**Checkpoint**: US1 works with fakes: one valid file from four agents and a reviewer.

---

## Phase 4: User Story 2 - Use chunked tracing from the app (Priority: P2)

**Goal**: a third pass in the app with a Haiku / Sonnet / Opus selector, expected time and cost
on its button, the chunk board while it runs, and the agent table after it.

**Independent test**: service and tracer tests with fakes run a chunked pass from
`begin_pass` to `export` (quickstart step 3); the owner's live run (quickstart step 4) shows the
board, the borders step and the table, and downloads one file.

- [X] T025 [P] [US2] In `tests/test_app_config.py`, test `ChunkedSettings`: the shipped config loads with all three choices; it fails for a missing choice, an `orchestrator` that names no entry, a model with no price in `[prices]`, `max_per_side` outside "1..4", `overlap_squares` not "< core_squares / 2", `core_squares` < 2; `expected((25, 25), "sonnet", detect=False) == (45, 0.29)` (within rounding), adding `[size_step]`'s seconds and cost when `detect=True`; a 13x13 map has no review in the figures; 50x50 with Opus gives 16 chunks and about $3.35; `expected_max("sonnet", detect=True)` gives the 16-chunk figures plus the size step (about 128 s and $1.04 with the shipped estimates).
- [X] T026 [US2] In `app/config.py`, add `AgentSettings`, `ReviewSettings`, `MergeSettings`, `ChunkedSettings` (fields and rules verbatim from data-model.md), `SizeStep.expected_seconds: float = 8`, `Settings.chunked`, and `ChunkedSettings.layout(map_size)`, `expected_max(agents, detect) -> (seconds, cost)` (the same formula for a `max_per_side` x `max_per_side` layout; FR-011) and `expected(map_size, agents, detect) -> (seconds, cost)`: "seconds = ceil(n / max_parallel) * per_chunk_s + review_s (n > 1) + size_step_s (detect)"; "cost = n * per_chunk_usd + review_usd (n > 1) + size_step_usd (detect)" (T025).
- [X] T027 [P] [US2] In `app/domain.py`, add `PassKind.chunked`, `AgentChoice = Literal["haiku", "sonnet", "opus"]`, the Pydantic models `ChunkReport(part, state, failure, seconds, cost_usd, views, walls, portals, lights)` and `ReviewReport(state, failure, model_label, seconds, cost_usd, removed, added)`, and on `TraceResult` the optional fields `agents`, `orchestrator_model`, `chunks: list[ChunkReport] = []`, `review: ReviewReport | None = None`, `untraced: list[tuple[Point, Point]] = []` (image fractions); reuse `ChunkState` and `ReviewState` from `llm`. In `tests/test_app_domain.py`, test that `tests/fixtures/golden_result.json` still loads and that a chunked `TraceResult` round-trips through JSON.
- [X] T028 [P] [US2] Create `app/progress.py` with `ChunkBoard` (one `threading.Lock`; `layout`, `seams`, chunk states, review state; `update_chunk(index, state)`, `update_review(state)`, `snapshot()` returning a copy, `done_count()`, `total`, `rebuild(layout, seams)`), and `tests/test_app_progress.py`: updates from several threads all land; a snapshot does not change after later updates; `done_count` counts `done` only; `rebuild` resets every state to `waiting`.
- [X] T029 [P] [US2] In `app/errors.py`, add `partial_message(parts: list[int], total, kind)` (`parts` are the 1-based part numbers; wording as in contracts/app.md, e.g. "Part 3 of 4 could not be traced (…)"; `kind=None` reads "the pass reached its time or cost limit"), `SEAMS_NOT_CHECKED`, and `short_reason(kind | None) -> str` for the table ("refused", "timed out", "service busy", "rate limited", "key problem", "no network", "unreadable answer", "limit reached", …), with tests in `tests/test_app_errors.py` that every `FailureKind` has a short reason and the partial message names each affected part by number and the total (FR-012).
- [X] T030 [US2] In `tests/test_app_tracer.py`, test `run_pass(..., kind=PassKind.chunked, agents=..., board=...)` with the `RoutingFake` from `tests/conftest.py` (T022): success gives a `TraceResult` with `kind == chunked`, `agents`, `orchestrator_model`, four `ChunkReport`s with counts, a `ReviewReport`, and summed cost and usage; one failed chunk gives a result with one `untraced` box; no chunk `done` gives a `PassFailure` with the first failed chunk's kind; all skipped gives `pass_limit`; a missing `ANTHROPIC_API_KEY` fails before any request; with the size step on, the board is rebuilt for the detected size before any agent starts; a failed review keeps the merged mask and `review.state == failed`; for every failure kind (refusal, limit, rate limit, provider busy, auth, network, timeout, unreadable), once for a chunk and once for the review, the outcome is a `TraceResult` or `PassFailure`, never an exception; `chunk_finished` (with part, window in squares, model, state, failure, turns, views, submissions, cost, seconds; FR-013), `review_finished` and `pass_finished` are logged with the fields of contracts/app.md (use the existing log capture pattern in `tests/test_app_logging.py`).
- [X] T031 [US2] In `app/tracer.py`, add the chunked branch to `run_pass` (new keyword arguments `agents` and `board`): the same key check and size step as today, `board.rebuild` when the size changed, `load_chunked_config(agents)`, `trace_chunks` with `deadline = start + deadline_s` of the choice and a callback updating `board`; build the `TraceResult` (fractions with `answer_to_fractions`, `ChunkReport`s with failure kinds from `classify`, `ReviewReport`, `untraced` as image fractions) or the `PassFailure`; log `chunk_finished`, `review_finished` and `pass_finished` / `pass_failed` with every field listed in contracts/app.md (T030).
- [X] T032 [P] [US2] In `tests/test_app_render.py`, test `chunk_overlay(image, snapshot, map_size)`: each core's outline is drawn and filled with its state's color (waiting grey, tracing blue, done green, failed red, skipped grey with a cross) and numbered; the strips are amber only while the review is `reviewing`; the input image is not changed; and `overlay(image, result)` outlines `result.untraced` in grey.
- [X] T033 [US2] In `app/render.py`, implement `chunk_overlay` and the untraced outlines in `overlay` (T032).
- [X] T034 [US2] In `tests/test_app_service.py`, test: `set_agents` accepts only the three choices; `can_start(session, chunked)` follows the `quick` rules; `begin_pass(chunked)` gives a ticket carrying `agents` and sets `session.board`; `finish_pass` clears it; `button_labels(settings, map_size, detect, agents)` gives e.g. "Chunked pass: 4 Sonnet agents (about 45 s, about $0.29, estimate)" and changes with the map size and choice; with `detect=True` it also shows the 16-part upper bound from `expected_max` (FR-011); the "Suggest walls" and "Deeper examination" labels are unchanged; `progress_line` adds " · 2 of 4 parts done" and then " · checking the borders"; `agent_table` gives 5 rows for a 2x2 result (4 parts + borders) with the columns of contracts/app.md and `None` after a `quick` pass; `status_line` names agents, orchestrator, time and cost; `result_message` shows the partial message (with part numbers) and/or `SEAMS_NOT_CHECKED`; `preview` draws the board while running. Update the existing tests that call `button_labels` or `PassTicket` to the new signatures, keeping their assertions about the two existing passes. Add the quickstart step 3 test: `begin_pass` → `run_pass(client=RoutingFake)` → `finish_pass` → `export`, and the file loads with `load_uvtt` with the final counts.
- [X] T035 [US2] In `app/service.py`, add `Session.agents` (from `[chunked].default_agents` in `prepare`) and `Session.board`, `set_agents`, `PassTicket.agents`, the chunked rules in `can_start`, `begin_pass`, `finish_pass`, the new `button_labels` signature with the chunked label, `progress_line`, `agent_table`, and the chunked forms of `preview`, `status_line` and `result_message`; the existing passes' behaviour does not change (T034).
- [X] T036 [US2] In `app/main.py` (wiring only), add under "Deeper examination" a `gr.Radio` "Agents' model" (labels from `[chunked.agents.*].label`, default Sonnet), the chunked button and its one-line note (contracts/app.md), and a read-only `gr.Dataframe` under the preview; extend `view()` and `outputs` with the radio, the button and the table (hidden when `agent_table` is `None`); add `on_agents` (radio `input` → `service.set_agents`, refresh labels) and `on_chunked` (pass `agents` and `board` to `tracer.run_pass` through `_pass`); while a chunked pass runs, each tick yields the board preview and `service.progress_line`, and the radio is locked; the size and detect events refresh the chunked label. Update the existing callers to the new `button_labels` and `run_pass` signatures (`view()`, `build_ui`, `_pass`, which today passes `run_pass` its arguments by position) so the two existing passes behave exactly as before (FR-016). Update the module docstring's Gradio notes for `gr.Radio` and `gr.Dataframe` after checking them against the installed Gradio 6.32.0 source.
- [X] T037 [US2] **(owner, paid ≈ $0.29)** Quickstart step 4: start the app, upload the castle reference map's image, keep 25x25 and Sonnet, run the chunked pass; check the button figures, the board and the borders step, the status line and the table; download the `.dd2vtt`, import it into Roll20 and check the walls at x = 12.5 and y = 12.5 (US1 acceptance 5, SC-007).

**Checkpoint**: the chunked pass works in the app with fakes, and live after T037.

---

## Phase 5: User Story 3 - Measure chunked tracing against the single session (Priority: P3)

**Goal**: score each agents choice on the reference maps the same way as the single-session
profiles, with the rule-merged and reviewed answers from the same run, and replace the
estimates with measured figures.

**Independent test**: `python -m llm.run --reference --chunked` with a fake client writes the
run folders and a `summary.csv` with both sets of scores, and asks before sending.

- [X] T038 [US3] In `tests/test_llm_run.py`, test `main(["--reference", "--chunked", "--agents", "sonnet", "--yes", "--run", <tmp>])` with `anthropic.Anthropic` monkeypatched to a `RoutingFake` and `RUNS` pointed at a temp folder: per map, `merged.json`, `answer.json`, `<map>.dd2vtt`, `preview.jpg`, `trace.json`, `merge.json`, `review/` and `chunks/<i>/` exist; `summary.csv` has `method`, `agents`, `orchestrator`, `chunks`, `chunks_failed`, `chunks_skipped`, `review`, `review_cost_usd`, the usual score columns and the same with a `merged_` prefix; `seam_gap_ends`, `duplicate_portals`, `duplicate_lights` and their `merged_` forms; without `--yes` the printed estimate is "chunks x per-chunk cost + review" per map and in total, and answering no sends nothing; a second run skips maps already traced.
- [X] T039 [US3] In `llm/run.py`, add `--chunked` and `--agents haiku|sonnet|opus` (default `[chunked].default_agents`; `--model`/`--effort` override the agents' model), the chunked estimate in `confirm`, the default run folder `runs/<YYYYMMDD-HHMMSS>_chunked_<agents>/`, a `save_chunked_map` that writes the files of contracts/config-and-cli.md, and the summary row with both score sets (`score_row` on `merged` and on `answer`) and both `merge.seam_checks` results (SC-003), traced on the true map size; update the module docstring's usage lines (T038).
- [X] T040 [US3] **(owner, paid ≈ $1.2)** Approve and run `python -m llm.run --reference --chunked --agents sonnet --run <date>_chunked_sonnet` (quickstart step 5).
- [X] T041 [US3] **(owner, paid ≈ $0.5; 16 parts per map since 23.11)** Approve and run `python -m llm.run --reference --chunked --agents haiku --run <date>_chunked_haiku` (output in `runs/<date>_chunked_haiku/`).
- [ ] T042 [US3] **(owner, optional, paid ≈ $3.8)** Approve and run `python -m llm.run --reference --chunked --agents opus --run <date>_chunked_opus` (output in `runs/<date>_chunked_opus/`), if the row is wanted for the slides.
- [X] T043 [US3] In `docs/results.md`, add a section "Chunked tracing · reference maps": one table per measured choice with the 13.11 reference columns plus agents, chunks and review state, the rule-merged scores beside the reviewed ones, run names, costs, sample size (one run per map), known weaknesses (one run per cell, 25x25 maps only, research.md R1), and the comparison with the 13.11 single-session rows against SC-001, SC-002, SC-003 (seam gaps and duplicates per map), SC-004, SC-005 and SC-009.
- [X] T044 [US3] In `llm/configs/claude.toml`, set each measured choice's `expected_seconds_per_chunk`, `expected_cost_per_chunk_usd` and the review's `expected_seconds` / `expected_cost_usd` from the measured means, set `estimate = false` for those choices, and replace their ESTIMATE comments with "measured <date> (docs/results.md)".

**Checkpoint**: chunked tracing is measured; the button shows measured figures.

---

## Phase 6: Polish & Cross-Cutting Concerns

- [X] T045 [P] Update `CLAUDE.md`: the Models section's chunked-pass bullet from "planned" to built (with measured figures once T043 is done), Repo layout (`llm/merge.py`, `llm/review.py`, `llm/orchestrator.py`, `app/progress.py`), and Pipeline conventions (a short "Chunked tracing" item: layout, overlap, rule merge, seam review).
- [X] T046 [P] Update `docs/PLAN.md` and the current week's file in `docs/roadmap/` with the chunked pass and its place in the presentation.
- [X] T047 [P] Add to `docs/lessons.md` the finding that the quarter views already exceed the reference maps' resolution, so chunking buys focus rather than detail at 25x25 (research.md R1), and any lesson from the US3 runs.
- [X] T048 Run the quality gate: `docker compose run --rm app pytest`, `docker compose run --rm app ruff check .`, `docker compose run --rm app ruff format --check .`; confirm every new module, function, test, fixture and nested helper has a docstring.
- [X] T049 Walk through steps 1-3 of `specs/002-chunked-map-tracing/quickstart.md` and confirm each expected outcome.

---

## Dependencies & Execution Order

### Phases

- **Setup (T001-T002)**: first. T002 must be done **before** any edit to `llm/agent.py` (T015).
- **Foundational (T003-T006)**: after Setup; blocks all stories.
- **US1 (T007-T024)**: after Foundational. It is the MVP.
- **US2 (T025-T037)**: needs US1's orchestrator (T023). T025-T029 and T032 can start as soon as
  Foundational is done, since they only touch config, domain, progress, errors and render.
- **US3 (T038-T044)**: needs US1 (T023). It does not need US2. T040-T042 are paid owner steps;
  T043-T044 follow them.
- **Polish (T045-T049)**: after the stories that are in scope.

### Within US1

T007 → T008 → (T009 → T010) → T011 → T012 → T013. T014 → T015 (needs T002, T004).
T016 → T017 → T018 → T019. T020 → T021 (needs T004, T015). T022 → T023 (needs T006, T012,
T015, T017, T019, T021) → T024.

### Within US2

T025 → T026; T027, T028, T029 in any order; T030 → T031 (needs T023, T026, T027, T028, T029);
T032 → T033 (needs T028); T034 → T035 (needs T031, T033); T036 (needs T035) → T037.

### Within US3

T038 → T039 → T040 → T041 → T042 (optional) → T043 → T044.

## Parallel Opportunities

- Foundational: T003 (views tests) and T005 (orchestrator config tests) are in different files.
- US1: T009 and T016 (merge tests) can be written while T014 (agent tests) and T020 (review
  tests) are written; implementations follow their tests.
- US2: T025, T027, T028, T029 and T032 touch different files and can go side by side, and can
  start while US1's orchestrator is still being built.
- US3 code (T038-T039) can be built alongside US2.

### Parallel example: US2 start

```
T025 tests/test_app_config.py      T027 app/domain.py + tests/test_app_domain.py
T028 app/progress.py + tests       T029 app/errors.py + tests/test_app_errors.py
T032 tests/test_app_render.py
```

## Implementation Strategy

### MVP first (US1 only)

1. Setup and Foundational (T001-T006).
2. US1 in task order: layout, merge and windowed agents (T007-T015), the review (T016-T021),
   then the orchestrator (T022-T024).
3. Stop and validate: quickstart steps 1-2; a fake four-agent run gives one valid file.

### Incremental delivery

1. US1 → a working orchestrator, testable from Python.
2. US2 → the app pass with selector, board and table; the owner's live run (T037) is the first
   paid step.
3. US3 → the batch mode and the owner-approved measurements; results in `docs/results.md`.
4. Polish → docs and quality gate.

### If time runs short before 2026-12-23

Keep: T001-T024, US2, T038-T040, T043-T045. Drop in this order: T042 (Opus run), then T041
(Haiku run). The seam review (T016-T021) is required by spec FR-020; dropping it needs the
owner to amend FR-020 first (plan.md, Delivery order). The orchestrator is wired so the pass
still works without a review (`review.state = skipped`, "borders not checked"), which keeps
that option open.

## Phase 7: Convergence

- [X] T050 CRITICAL: In `tests/test_app_tracer.py`, test that a chunk agent stopped by its own turn or cost limit with no submission reports failure `pass_limit`, and one that finishes without ever submitting reports `unreadable`; and the same two for the seam review (`review.failure`), each giving a `TraceResult`, never an exception, per Constitution IV / FR-012 (missing)
- [X] T051 In `llm/orchestrator.py` (`trace_chunks`), cap the seam review's cost at the whole-map budget still left (the choice's `max_cost_usd` minus what the agents spent), by passing `min([chunked.review].max_cost_usd, remaining)` to `review_seams` through `cfg["review"]`; test in `tests/test_llm_orchestrator.py` that a review cannot take the pass past `max_cost_usd`, per FR-020 / FR-010 (partial)
- [X] T052 In `app/tracer.py`, log the merge's dropped duplicates in `pass_finished` (`portals_dropped` and `lights_dropped` as totals from `MergeReport`), add both names to `ALLOWED` in `app/logging.py`, and assert them in the chunked logging test in `tests/test_app_tracer.py`, per FR-013 (partial)
- [X] T053 Count the map-size step's cost toward the chunked pass's whole-map limit: give `llm/orchestrator.trace_chunks` an optional `spent_before: float = 0.0` added to `spent()`, pass the size step's cost from `app/tracer.py` and `llm/run.py`, and test that a size step that used the budget skips every chunk, per FR-010 (partial)
- [X] T054 Read the chunked pass's default agents choice from config instead of a literal: in `llm/run.py` replace `load_chunked_config("sonnet")["chunked"]["default_agents"]` with a small `default_agents()` in `llm/orchestrator.py` that reads `[chunked].default_agents`, and in `app/service.py` give `Session.agents` no hard-coded `"sonnet"` (set only by `prepare`); test `default_agents()` in `tests/test_llm_orchestrator.py`, per plan: defaults live in config (partial)
- [X] T055 In `tests/test_llm_merge.py`, test that the merge keeps a door gap open next to a seam: a wall with a door gap just left of x = 12.5 and one straddling it (traced by both neighbours) comes out with no wall across the door, per FR-008 (partial)

## Phase 8: Per-model part size (clarified 2026-11-23 after T037)

**Purpose**: Haiku needs smaller parts than Sonnet and Opus (owner, after the first live runs).
Each part keeps its own fresh agent session, at most 4 at once; the 16-part cap stays.

- [X] T056 In `llm/configs/claude.toml`, move `core_squares` from `[chunked]` into each `[chunked.agents.*]` entry (haiku 7, sonnet 13, opus 13); in `llm/orchestrator.load_chunked_config` put the choice's `core_squares` in `cfg["chunked"]`; test in `tests/test_llm_orchestrator.py` that each choice gets its size and that Haiku traces 16 parts on 25 x 25 with at most 4 agents running at once, per spec clarification 23.11 / FR-003
- [X] T057 In `app/config.py`, add `AgentSettings.core_squares` (>= 2), remove `ChunkedSettings.core_squares`, check the overlap against every choice's size, and give `layout(map_size, agents)` and `expected` the choice's size; update `app/service.py` (board, button label) and `app/tracer.py` (board rebuild); tests in `tests/test_app_config.py` and `tests/test_app_service.py`, per FR-003 / FR-018
- [X] T058 In `app/service.py`, word the button and status line as parts and agents ("16 parts on 4 Haiku agents"), since parts now outnumber the agents working at once; tests in `tests/test_app_service.py`, per FR-018 / FR-019
- [X] T059 Update `spec.md` (clarification, FR-003, assumptions), `research.md`, `data-model.md`, `contracts/`, `plan.md`, `quickstart.md`, `CLAUDE.md` and `docs/roadmap/week-06.md` for the per-model part size and the new Haiku estimate (about $0.13 per 25 x 25 map)

## Phase 9: Convergence

- [X] T060 Resolve the conflict between the per-model part size and SC-004 for Haiku: with 7-square parts a 25 x 25 Haiku pass is 16 parts at 4 agents at a time, estimated at about 140 s, while SC-004 allows at most twice Haiku's single-session time (31-36 s on 13.11, so about 70 s). Either (a) the owner amends SC-004 in `spec.md` (for example "for Sonnet and Opus", or a separate bound for Haiku) and `plan.md`'s performance line, or (b) make `max_parallel` a per-model setting in `llm/configs/claude.toml` / `app/config.py` (Haiku 8, tested in `tests/test_app_config.py` and `tests/test_llm_orchestrator.py`) and re-estimate; record the choice in the spec's Clarifications, per SC-004 / spec clarification 23.11 (contradicts)

## Phase 10: Merge fixes from the live Haiku runs (2026-11-23)

**Purpose**: the owner's 16-part Haiku runs showed walls joined wrongly and wall pieces
missing (research.md R4, revised 23.11). Each bug has a test that reproduced it first.

- [X] T061 In `llm/merge.py`, place inner borders at quarter squares (`_off_grid`, `_cuts`) so seams never lie on whole or half squares; test in `tests/test_llm_merge.py`, per FR-008 / FR-001
- [X] T062 In `llm/merge.py`, keep walls along a seam from both sides and keep one when both neighbours drew it (`_dedupe_along_seams`, `MergeReport.walls_deduped`, logged in `app/tracer.py`); tests for the lost, doubled and one-sided cases, per FR-008 / FR-013
- [X] T063 In `llm/merge.py`, replace transitive snapping with one-to-one pairing across a seam (`_pair_and_join`): ends from different parts, on opposite sides of the seam, within the tolerance of it and of each other, closest first, never through a door; also used by `apply_review` at strip edges; tests for same-side ends, chains, doors, small gaps, and a wall beside a seam, per FR-008
- [X] T064 Add a seeded test of imperfect agents on a grid-aligned 26 x 28 map (perfect agents F1 >= 0.99; agents stopping at their own area F1 >= 0.94, no hanging seam ends) in `tests/test_llm_merge.py`, and update `research.md`, `data-model.md`, `contracts/orchestrator.md`, `CLAUDE.md` and `docs/lessons.md`, per SC-003

