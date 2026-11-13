---

description: "Task list for the battlemap tracer app"
---

# Tasks: Battlemap Tracer App

**Input**: Design documents from `/specs/001-battlemap-tracer-app/`

**Prerequisites**: plan.md, spec.md, research.md, data-model.md, contracts/, quickstart.md

**Tests**: included. The constitution (IV) requires a pytest test for every module that
transforms data and for every failure cause, and the plan lists the tests. Tests never make
a paid call: they use the scripted `FakeClient` from `tests/test_llm_agent.py` and recorded
responses in `tests/fixtures/`.

**Organization**: by user story, in the spec's priority order. Each story ends at a
checkpoint where it can be tried on its own.

## Format: `[ID] [P?] [Story] Description`

- **[P]**: can run in parallel (different files, no dependency on an unfinished task)
- **[Story]**: the user story the task belongs to (US1 to US5)

## Rules that apply to every task

- Python only. Docstrings on every module, function, test, fixture and nested helper; type
  hints on public functions (CLAUDE.md, constitution IV).
- Run everything through Docker Compose: `docker compose run --rm app pytest`,
  `docker compose run --rm app ruff check .`, `docker compose run --rm app ruff format --check .`.
- No task makes a paid model call except T058 and T062, which are the owner's to approve.
- Do not change the tracing logic, prompt (`SYSTEM`), tools or views in `llm/agent.py` and
  `llm/views.py` beyond what a task names: the measured scores depend on them.
- Do not touch `train/`, `data/generator.py`, `data/synth/` or `notebooks/` (frozen).
- Commit only when the owner asks.

---

## Phase 1: Setup (Shared Infrastructure)

**Purpose**: dependency management with `uv`, the two new packages, the reference maps.

- [X] T001 Declare dependencies for `uv` in `pyproject.toml`: add `torch` and `torchvision` to `dependencies` with a `[[tool.uv.index]]` entry named `pytorch-cpu` (`https://download.pytorch.org/whl/cpu`, `explicit = true`) and `[tool.uv.sources]` pointing both packages at it; add `gradio` and `pydantic>=2`; move `pytest` and `ruff` to a `dev` dependency group; keep every existing dependency and its comment; add a dated comment for each new package (research.md R11, R12)
- [X] T002 Rewrite `Dockerfile` to install with `uv`: copy the `uv` binary from a pinned `ghcr.io/astral-sh/uv` image, keep `ubuntu:24.04`, the venv at `/opt/venv`, the `ubuntu` user and `CMD ["pytest"]`; install with `uv sync --frozen` into that venv (dependencies in their own layer before `COPY . .`); keep the image CPU-only; comment every step
- [X] T003 Generate and commit-ready `uv.lock` (`uv lock`), build the image (`docker compose build`) and run the whole existing suite (`docker compose run --rm app pytest`); the task is done only when every existing test passes and `python -c "import torch; print(torch.cuda.is_available())"` prints `False`. If the CPU index cannot be made to work, stop and report: the fallback in research.md R11 is to keep `pip`
- [X] T004 [P] Create `data/reference/` with copies of `data/raw/dungeondraft/dd04_a.dd2vtt`, `dd06_a.dd2vtt`, `dd07_a.dd2vtt` and `dd04_d.dd2vtt`, and a `data/reference/README.md` naming each map's role (tavern: ordinary building; mine: cave; castle; tavern with no grid), that they are the owner's own Dungeondraft exports, and that labels come only from these files (research.md R9)
- [X] T005 [P] Add `data/test/` to `.gitignore` with a comment (published third-party maps are never committed) and confirm `git status` shows `data/reference/` as addable and `data/test/` as ignored
- [X] T006 [P] Create `tests/fixtures/` with a `README.md` saying what goes there: recorded model responses as JSON (text and tool calls only, no images, no key), the golden export file, and small generated images
- [X] T007 [P] Update the comments in `docker-compose.yml`: the header line (tests, data tools, the tracer and the app), and the port comment with the app's start command `docker compose run --rm --service-ports app python -m app.main`

**Checkpoint**: the image builds with `uv`, all existing tests pass, the reference maps are in place.

---

## Phase 2: Foundational (Blocking Prerequisites)

**Purpose**: config, domain models, failure kinds and logging that every story uses.

**⚠️ CRITICAL**: no user story work starts until this phase is done.

- [X] T008 Replace the `[model]` table in `llm/configs/claude.toml` with `[profiles.quick]` and `[profiles.deep]`, and add `[lights.small|medium|large]` and `[app]`, exactly as in `contracts/config-and-cli.md` (quick: `claude-sonnet-5-5`, label "Sonnet 5.5", effort `medium`, `deadline_s = 60`, `expected_seconds = 20`, `expected_cost_usd = 0.07`; deep: `claude-opus-5-5`, label "Opus 5.5", effort `medium`, `deadline_s = 180`, `expected_seconds = 60`, `expected_cost_usd = 0.27`; both `max_tokens = 16000`, `fallbacks = true`; lights `range` 8.0 / 12.0 / 16.0, `intensity` 1.0; app `max_upload_mb = 20`, `min_squares = 1`, `max_squares = 200`, `default_width = 25`, `default_height = 25`, `export_ppg = 70`, `export_jpeg_quality = 90`); keep `[limits]`, `[views]`, `[prices]` and the file's comments
- [X] T009 Change `load_config` in `llm/agent.py` to `load_config(profile: str = "quick", path: Path = CONFIG) -> dict`, returning the config with `cfg["model"]` set to a copy of `cfg["profiles"][profile]` so `trace_map` and `_request` are untouched; update `llm/run.py` to call it and keep `--model` / `--effort` overriding `cfg["model"]`; add tests to `tests/test_llm_agent.py` that `load_config("quick")` gives `claude-sonnet-5-5` and `load_config("deep")` gives `claude-opus-5-5`, both at effort `medium`, and fix the existing tests' `load_config()` calls
- [X] T010 [P] Create `app/config.py`: Pydantic v2 models `Profile` (`name`, `label`, `effort`, `max_tokens`, `fallbacks: bool`, `deadline_s`, `expected_seconds`, `expected_cost_usd`), `Limits`, `Views`, `Price` (`input`, `output`), `LightSpec` (`range`, `intensity`), `AppLimits`, and `Settings` holding `profiles`, `limits`, `views`, `prices`, `lights`, `app`; `load_settings(path=CONFIG) -> Settings`; validation: every profile's model id must have a price entry, the three light tiers `small`, `medium`, `large` must all be present, `deadline_s > 0` (data-model.md "Settings")
- [X] T011 [P] Create `tests/test_app_config.py`: the shipped config loads; a profile whose model has no price fails; a missing light tier fails; `deadline_s = 0` fails; the `[lights]` table equals `LIGHT_TIERS` ranges in `data/rasterize.py` (8 / 12 / 16)
- [X] T012 [P] Create `app/domain.py`: Pydantic v2 models `Point` (`fx`, `fy`, each clamped to 0..1), `Wall` (`points: list[Point]`, at least 2), `Portal` (`a`, `b`, which must differ), `LightTier` (`small | medium | large`), `Light` (`at`, `tier`), `MapSize` (`width`, `height`, each a whole number 1..200), `MapSizeSource` (`default | typed | detected | not_found`), `PassKind` (`quick | deep`), `Usage`, `TraceResult` (fields as in data-model.md), `RawAnswer` (the model's tool input in grid squares: `walls[].points[]{x,y}`, `arcs[]{cx,cy,r,start_deg,end_deg}`, `portals[]{x1,y1,x2,y2}`, `lights[]{x,y,tier}`); and the conversion functions: `answer_to_fractions(raw, traced_size, image_size)` using `ppg = image_width / map_width` on both axes (`fx = x / map_width`, `fy = y * ppg / image_height`), arcs turned into polylines with `postprocess.uvtt.arc_points` first, walls with fewer than 2 points dropped; `to_grid(point, map_size)` (`x = fx * map_width`, `y = fy * map_height`); `to_pixels(point, image_size)`
- [X] T013 [P] Create `tests/test_app_domain.py`: a point at grid (5, 5) on a 10 x 10 map of a 700 x 700 image becomes fractions (0.5, 0.5); on a 700 x 1400 image with a 10 x 10 entered size, grid `y = 10` becomes `fy = 0.5` (the proportions case in research.md R2); values just outside 0..1 are clamped; an arc becomes a polyline; a one-point wall is dropped; a `MapSize` of 0 or 201 or 2.5 fails; a portal with equal ends fails; `to_grid` round-trips `answer_to_fractions` on a square-cell map
- [X] T014 [P] Create `app/errors.py`: `FailureKind` (`refusal | output_limit | pass_limit | rate_limit | provider_busy | auth | missing_key | network | timeout | unreadable | unexpected`), `PassFailure` (`kind`, `kind_of_pass`, `elapsed_s`, `usage`, `cost_usd`, `detail` for the log only), `UploadRejected` (`reason: wrong_type | too_large | not_an_image`), `MapSizeInvalid`, and `message(kind, has_earlier_mask) -> str` returning the exact texts in `contracts/ui.md`, with "Your earlier mask is still here." appended when `has_earlier_mask` is true; upload and map-size messages as in the same table
- [X] T015 [P] Create `tests/test_app_errors.py`: every `FailureKind` has a non-empty message; no message contains "Traceback", "Error:" or an exception class name; the earlier-mask sentence appears only when asked; each `UploadRejected` reason and `MapSizeInvalid` has its message from `contracts/ui.md`
- [X] T016 [P] Create `app/logging.py`: `log_event(event: str, **fields)` writing one JSON object per line through the standard `logging` module (logger `battlemap`), and `setup_logging()`; allowed fields: profile, model id, served-by, elapsed seconds, token counts, estimated cost, stop reason or failure kind, map size and its source; it must drop any field named `image`, `answer`, `key` or `api_key` and never log coordinates (research.md R15)
- [X] T017 [P] Create `tests/test_app_logging.py`: a logged event is one parseable JSON line with the given fields; a field named `api_key` or `image` is not in the output; the value of `ANTHROPIC_API_KEY` set in the test environment never appears in any log line
- [X] T018 Add a `lights` parameter to `answer_to_uvtt` and `_light` in `postprocess/uvtt.py` (a mapping tier -> `{range, intensity}`, default built from `LIGHT_TIERS` with intensity 1) so `range` and `intensity` come from the table passed in; nothing else changes; extend `tests/test_uvtt_writer.py`: the default output is unchanged, and a custom table changes the written `range` and `intensity`

**Checkpoint**: config, domain, failures and logging exist and are tested. Stories can start.

---

## Phase 3: User Story 1 - Fast suggestion to a downloadable file (Priority: P1) 🎯 MVP

**Goal**: upload an image, type the map size, click "Suggest walls", see the mask, click
"Accept mask", get a file Roll20 imports.

**Independent Test**: quickstart.md scenario A, with the map size typed (the detect option
arrives in US4; until then the app always uses the size in the fields).

### Tests for User Story 1

> Write these first and see them fail.

- [X] T019 [P] [US1] Create `tests/fixtures/responses_quick_ok.json` (a recorded-style script of model responses: one `submit_answer` tool call with 2 walls, 1 arc, 1 portal and 1 light on a 10 x 10 map, then a closing text) and a helper in `tests/conftest.py` that loads such a file into the scripted `FakeClient` (move `FakeClient`, `reply`, `call`, `text` from `tests/test_llm_agent.py` into `tests/conftest.py` so both test files share them)
- [X] T020 [P] [US1] Create `tests/test_app_tracer.py`: with the fixture client, `run_pass(image, MapSize(10, 10), fallback, PassKind.quick, settings, client)` returns a `TraceResult` whose counts match the fixture, whose coordinates are fractions in 0..1, whose `model_id` is `claude-sonnet-5-5`, `effort` is `medium`, `cost_usd > 0`, `traced_size` is 10 x 10 and `size_source` is `typed`; the request sent to the client used the quick profile's model; with `ANTHROPIC_API_KEY` unset and no client, the result is a `PassFailure` of kind `missing_key` and no request was made
- [X] T021 [P] [US1] Create `tests/test_app_exporter.py` with the checks in `contracts/export-file.md` "What a test checks": loads with `data.rasterize.load_uvtt`; `pixels_per_grid` is 70; `map_size` as given; decoded image is `map_size * 70` px each way; a wall at fractions (0.2, 0.4)–(0.6, 0.4) comes out at (4, 4)–(12, 4) on 20 x 10 and (8, 8)–(24, 8) on 40 x 20; each tier writes its table `range` and `intensity`; `.dd2vtt` and `.uvtt` bytes are identical; an empty mask writes empty lists; and the golden test: `tests/fixtures/golden_result.json` plus a generated 200 x 200 image produce JSON equal to `tests/fixtures/golden_export.uvtt`, with the `image` field compared by decoded size only
- [X] T022 [P] [US1] Create `tests/test_app_render.py`: `overlay(image, None)` returns an equal copy; with a result, pixels along a wall, a portal and a light differ from the input and the three use three different colors; the input image is not modified; the output size equals the input size
- [X] T023 [P] [US1] Create `tests/test_app_service.py` (US1 part): `prepare` accepts `.png`, `.jpg`, `.jpeg`, `.webp` and returns a `Session` with map size 25 x 25, no mask and a new token; it raises `UploadRejected` for `.gif`, for a file over 20 MB and for a text file renamed `.png`, without creating a client; `begin_pass` + `finish_pass` with a `TraceResult` puts the mask on the session; `preview` returns an image; `export` writes `<image name>.dd2vtt` in the session temp folder and raises when there is no mask; `status_line` contains "Sonnet 5.5 (medium)", the seconds, the cost and the counts; a second `prepare` gives a new token and no mask; `close` removes the temp folder

### Implementation for User Story 1

- [X] T024 [US1] Create `app/tracer.py` with `run_pass(image, map_size, fallback_size, kind, settings, client=None) -> TraceResult | PassFailure` for the given-size path: return `missing_key` when `ANTHROPIC_API_KEY` is unset and no client is passed; call `llm.agent.load_config(kind)` and `llm.agent.trace_map`; validate `trace.answer` into `RawAnswer`; convert with `answer_to_fractions`; fill `note`, `kind`, `model_id`, `served_by`, `effort`, `elapsed_s`, `usage`, `cost_usd`, `traced_size`, `size_source`; wrap the whole body so no exception leaves the function (anything unmapped becomes `unexpected` for now; the full mapping is T039); log one `pass_finished` event with `app.logging`
- [X] T025 [P] [US1] Create `app/exporter.py`: `build(result, map_size, image, settings) -> dict` converting fractions to grid squares with `to_grid`, resizing the image to `map_width * 70` by `map_height * 70` px (`export_ppg`), encoding JPEG at `export_jpeg_quality`, and calling `postprocess.uvtt.answer_to_uvtt` with `settings.lights`; `write(path, payload)`; output exactly as in `contracts/export-file.md`
- [X] T026 [P] [US1] Create `app/render.py`: `overlay(image, result | None) -> Image` drawing walls, portals and lights in three distinct colors (reuse `WALL_RGB`, `PORTAL_RGB`, `LIGHT_RGB` from `llm/views.py`) on a copy, line width scaled to the image's longer side, lights as rings; returns the image alone when `result` is `None`
- [X] T027 [US1] Create `app/service.py` (US1 part): the `Session` class with the fields in data-model.md; `prepare`, `can_start`, `begin_pass` (returns a `PassTicket` with token, kind, start time and the map size on screen), `finish_pass`, `preview`, `export`, `status_line`, `button_labels`, `close`, as in `contracts/service.md`; `prepare` checks extension, size (`max_upload_mb`) and that Pillow opens the file, converts to RGB and creates the temp folder with `tempfile.mkdtemp`
- [X] T028 [US1] Read the documentation of the Gradio version in `uv.lock` for: `gr.Blocks`, `gr.State`, file or image upload with allowed types, the server's upload size limit, `gr.DownloadButton`, enabling and disabling components from a handler, generator handlers, and session-end cleanup; write what was found, with the version number, as a comment block at the top of `app/main.py` (research.md R13 lists these as to be verified, not assumed)
- [X] T029 [US1] Create `app/main.py`: a `gr.Blocks` page wired only to `app/service.py`, with the controls for this story from `contracts/ui.md`: upload (three types, 20 MB) with the notice "Your image is sent to Anthropic, a third-party AI provider, for analysis."; map width and height pre-filled 25 and 25; "Suggest walls" with its expected time and cost from `button_labels`; the preview with a legend; the status line; the message area; the `.dd2vtt` / `.uvtt` choice; "Accept mask" visible always and enabled only with a mask; a new upload clears mask, status and messages; `main()` launches on `0.0.0.0:7860`; run as `python -m app.main`
- [X] T030 [US1] Show the empty-mask message ("Nothing was found on this map: no walls, doors, windows or lights.") in `app/service.py` / `app/main.py` when a pass succeeds with no walls, portals or lights, keep "Accept mask" enabled for it, and add the case to `tests/test_app_service.py`

**Checkpoint**: quickstart.md scenario A works with a typed map size. This is the MVP.

---

## Phase 4: User Story 2 - Deeper examination of a hard map (Priority: P2)

**Goal**: once a suggestion exists, re-trace from scratch with the stronger model and replace the mask.

**Independent Test**: quickstart.md scenario B.

### Tests for User Story 2

- [X] T031 [P] [US2] Add to `tests/test_app_service.py`: `can_start(session, deep)` is false with no mask and true with one; a deep `finish_pass` replaces the earlier mask and the earlier one cannot be got back; `status_line` then shows "Opus 5.5 (medium)"; `button_labels` gives "about 20 s, about $0.07" for the fast button and "about 60 s, about $0.27" for the deep one, read from the config
- [X] T032 [P] [US2] Add to `tests/test_app_tracer.py`: `run_pass(..., PassKind.deep, ...)` sends requests with model `claude-opus-5-5` and effort `medium`, sends no part of an earlier answer (a fresh trace), and prices the result with the Opus price entry

### Implementation for User Story 2

- [X] T033 [US2] Add "Deeper examination" to `app/main.py`: its label with expected time and cost, enabled only when a mask is on screen, running the deep profile through the same handler as the fast pass; repeatable
- [X] T034 [US2] Add the always-visible note beside it in `app/main.py`, text exactly as in `contracts/ui.md`: "The fast pass handles ordinary buildings well but often misses cave outlines and doors in castles and other complex structures. The deeper examination fixes most of that."

**Checkpoint**: quickstart.md scenarios A and B work.

---

## Phase 5: User Story 3 - Staying in control while a pass runs or fails (Priority: P3)

**Goal**: progress with elapsed time, locked pass buttons, a plain message for every
failure, the earlier mask kept, late results dropped.

**Independent Test**: quickstart.md scenario C, plus the fake-client tests for the failure
kinds that cannot be produced by hand.

### Tests for User Story 3

- [X] T035 [P] [US3] Add to `tests/test_llm_agent.py`: with `deadline` already passed, `trace_map` makes no request and returns `stopped == "timeout"`; with a deadline that passes after the first response, the loop stops before the second request; each request carries a `timeout` no larger than the time left; the raw responses (text and tool calls) are kept on the `Trace`
- [X] T036 [P] [US3] Add to `tests/test_app_tracer.py` one test per row of the failure table in `contracts/ui.md`, each asserting the `FailureKind` and that nothing is raised: stop reason `refusal` -> `refusal`; `max_tokens` -> `output_limit`; turn limit or cost limit with no answer -> `pass_limit`; a client raising `anthropic.RateLimitError` -> `rate_limit`; another `anthropic.APIStatusError` (status 529) -> `provider_busy`; `AuthenticationError` and `PermissionDeniedError` -> `auth`; `APIConnectionError` -> `network`; `APITimeoutError` and a passed deadline -> `timeout`; a submitted answer that fails `RawAnswer` validation and a loop that ends with no submission -> `unreadable`; a `RuntimeError` from the client -> `unexpected`; in every case `detail` is set and the usage spent so far is reported
- [X] T037 [P] [US3] Add to `tests/test_app_service.py`: `finish_pass` with a `PassFailure` keeps `session.result`, sets `last_failure` and clears `running`; `status_line` still shows the last successful pass, not the failed one; `finish_pass` with a ticket whose token is stale returns `False` and changes nothing; `begin_pass` while a pass is running is refused; `export` works while `running` is set; after any failure `begin_pass` works again

### Implementation for User Story 3

- [X] T038 [US3] Add `deadline: float | None = None` to `trace_map` in `llm/agent.py`: before each request, stop with `trace.stopped = "timeout"` if the deadline has passed, and pass the remaining seconds as the request `timeout`; keep each response's text and tool-call blocks in a new `Trace.responses` list; change nothing else in the loop
- [X] T039 [US3] Complete the failure mapping in `app/tracer.py` as in research.md R6 and the table in `contracts/ui.md`: stop reasons, the loop's `stopped` values (`turn limit`, `cost limit`, `timeout`), each `anthropic` exception class, validation errors, no submission, and the catch-all; pass `deadline = start + profile.deadline_s`; log a `pass_failed` event with the kind and `detail`, never the key
- [X] T040 [US3] Make the pass handler in `app/main.py` a generator that starts `run_pass` in a worker thread, yields "Working… N s" about once a second, keeps both pass buttons disabled until the pass ends, and leaves "Accept mask" and the preview as they are while it runs; on finish it calls `finish_pass` and shows either the new mask and status or the failure message from `app.errors.message`
- [X] T041 [US3] Drop late results in `app/main.py` and `app/service.py`: when `finish_pass` returns `False` (the token changed because of a new upload), show nothing from that pass and log a `pass_dropped` event with its cost; make sure a new upload during a pass re-enables the fast button for the new image
- [X] T042 [US3] Add session cleanup in `app/main.py`: call `service.close(session)` when the browser session ends, using the mechanism found in T028, so the temp folder is removed (FR-030); add a test in `tests/test_app_service.py` that `close` is safe to call twice
- [X] T043 [US3] Make sure no stack trace can reach the page: wrap each handler in `app/main.py` so an unexpected exception is logged and shown as the `unexpected` message, and start the app with Gradio's error display turned off

**Checkpoint**: quickstart.md scenarios A to C work; every failure kind has a passing test.

---

## Phase 6: User Story 4 - Map size worked out by the model (Priority: P4)

**Goal**: with "detect map size from the image" on, the pass works out the size in squares,
fills in the fields, and traces on that grid; no grid found falls back to the size in the fields.

**Independent Test**: quickstart.md scenario D.

### Tests for User Story 4

- [X] T044 [P] [US4] Add to `tests/test_llm_agent.py`: `detect_map_size` sends one request offering only the `report_map_size` tool; a reply `{grid_found: true, width: 26, height: 28}` returns `(26, 28)`; `grid_found: false` returns `None`; a size of 0 or 201 returns `None`; a reply with no tool call returns `None`; its token usage is added to the `Trace` passed in
- [X] T045 [P] [US4] Add to `tests/test_app_tracer.py`: `run_pass` with `map_size=None` and a script that first reports 12 x 8 then submits an answer returns `traced_size` 12 x 8 and `size_source == detected`, with usage and cost covering both steps; with "no grid" it traces on `fallback_size` and returns `size_source == not_found` as a success, not a failure; a failure during the detection step returns a `PassFailure` of the matching kind
- [X] T046 [P] [US4] Add to `tests/test_app_service.py`: a new session has `detect_size` on; `begin_pass` then gives a ticket with map size `None`; after a `detected` result the session's map size is the detected one, its source is `detected` and `detect_size` is off; after `not_found` the map size is unchanged and the no-grid message is set; `set_map_size` turns `detect_size` off and a later ticket carries the typed size; a size typed while the pass was running is not overwritten by the detected one; a deep pass after a detection uses the size on screen unless `set_detect(session, True)` was called; a failed pass leaves the fields as they were

### Implementation for User Story 4

- [X] T047 [US4] Add to `llm/agent.py` the `report_map_size` tool (strict schema: `grid_found: boolean`, `width: integer`, `height: integer`), a short `SIZE_SYSTEM` prompt (count the map's grid squares across and down; square grids only; say `grid_found: false` when there is no visible square grid or it cannot be counted), and `detect_map_size(image, cfg, client, trace) -> tuple[int, int] | None`: one request with the whole map downscaled to `views.max_px` and the top and left edge strips at higher zoom, no grid overlay; add its usage to `trace`; return `None` for no grid, no tool call, or a size outside 1..200 (research.md R3)
- [X] T048 [US4] Extend `run_pass` in `app/tracer.py`: when `map_size` is `None`, call `detect_map_size` first inside the same deadline and the same `Trace`, trace on the detected size or on `fallback_size`, and set `size_source` to `detected` or `not_found`; log the map size and its source
- [X] T049 [US4] Extend `app/service.py`: `set_detect`; `begin_pass` sends `None` when `detect_size` is on; `finish_pass` applies the rules in data-model.md "State transitions" (set the size and turn the option off on `detected`; leave the size on `not_found`; never overwrite a size typed during the pass)
- [X] T050 [US4] Add to `app/main.py` the "Detect map size from the image" checkbox (on for every new upload, off when the user types a size or a size is detected) and the map size note showing "Detected from the image" or "No grid was found in the image, so the map size shown was used. Check it and correct it if needed; that costs nothing."; the pass buttons may start with the option on even though the fields hold the default

**Checkpoint**: quickstart.md scenario D works; detection adds no separate paid action.

---

## Phase 7: User Story 5 - Correcting the map size without paying again (Priority: P5)

**Goal**: changing the map size with a mask on screen keeps the mask over the same image
features and rebuilds the download, with no pass.

**Independent Test**: quickstart.md scenario E.

### Tests for User Story 5

- [X] T051 [P] [US5] Add to `tests/test_app_service.py`: with a mask on screen, `set_map_size(session, 26, 28)` leaves `session.result` identical, makes no client call, and `preview` returns the same pixels as before; `export` then writes `map_size` 26 x 28 with every coordinate scaled (a point at fractions (0.5, 0.5) is at (13, 14)) and an image of 1820 x 1960 px; each light keeps its tier; `set_map_size` with 0, 201, 2.5 or an empty value raises `MapSizeInvalid` with the range message and changes nothing; a size that makes cells non-square (more than 5% apart) returns the proportions warning and still applies

### Implementation for User Story 5

- [X] T052 [US5] Implement `set_map_size` in `app/service.py` as in `contracts/service.md`: validate, set source `typed`, turn the detect option off, return the proportions warning when `image_width / width` and `image_height / height` differ by more than 5%
- [X] T053 [US5] Wire the map size fields in `app/main.py`: on change call `set_map_size`, show the range message or the proportions warning in the map size note, redraw the preview and rebuild the download file at once; also rebuild the download when the extension choice changes; a pass button click with an invalid size shows the range message and starts nothing (FR-003, SC-008)

**Checkpoint**: all five stories work; quickstart.md scenarios A to E pass.

---

## Phase 8: Evaluation, docs and polish

**Purpose**: prove the success criteria with numbers, and leave the repo consistent.

- [X] T054 [P] Add `portal_recall(pred_uvtt, true_uvtt, tolerance=0.5) -> float` to `eval/metrics.py`: a labeled portal counts as found when a predicted portal's midpoint lies within `tolerance` squares of its midpoint, matched one to one (greedy by distance); 1.0 when there are no labeled portals; add tests to `tests/test_metrics.py` (perfect match 1.0, none found 0.0, two predictions near one label count once, a prediction 0.6 squares away does not count)
- [X] T055 Extend `llm/run.py` as in `contracts/config-and-cli.md`: `--profile quick|deep` (default `quick`), `--reference` (trace every `.dd2vtt` in `data/reference/`, taking the image, the true map size and the labels from the file itself with `data.rasterize.decode_image`, `rasterize_mask` and `load_uvtt`), `--detect-size` (call `detect_map_size`, record true size, detected size and whether it was right; score on the true size), `--yes`; without `--run` use `runs/<YYYYMMDD-HHMMSS>_<profile>/`; before the first call print the number of maps and `expected_cost_usd` x maps and ask to continue unless `--yes`; write `responses.json` per map from `Trace.responses`; add `portal_recall`, `profile`, `true_size`, `detected_size` and `size_right` to `summary.csv`
- [X] T056 [P] Create `tests/test_llm_run.py`: with the fake client patched in and a temp run folder, `--reference --profile deep --yes` on a one-map reference folder writes `responses.json`, `trace.json`, `answer.json`, the `.dd2vtt`, `preview.jpg` and a `summary.csv` row with `portal_recall` and `profile`; without `--yes` and with "n" on stdin no request is made; a map already traced is skipped without `--redo`; `responses.json` contains no base64 image data
- [X] T057 Run `docker compose run --rm app pytest`, `ruff check .` and `ruff format --check .` and fix what they report; check every new module, function, test and fixture has a docstring
- [X] T058 **Owner's approval needed (paid, about $1.40 in all).** Run the reference evaluation from quickstart.md section 4: `python -m llm.run --reference --profile quick --detect-size` and the same with `--profile deep`; compare with the thresholds there (SC-003, SC-004, SC-009); repeat a run that falls slightly under a floor before calling it a regression
- [X] T059 Record the reference runs in `docs/results.md` as a new dated section: the table (per map and profile: wall IoU, wall boundary F1, portal IoU, portal recall, light IoU, map size right, cost, time), the run names, the total cost, the number of runs per cell, and a line on how the map-size step changed time and cost
- [X] T060 Update `expected_seconds` and `expected_cost_usd` in `llm/configs/claude.toml` to the measured values with the map-size step, and the same figures in `README.md`, `CLAUDE.md` ("Models" table) and `docs/PLAN.md`; if map-size accuracy is under 80%, record it and revise SC-009 in `spec.md` with the owner
- [X] T061 [P] Update the docs to the built state: `README.md` (status boxes, the app's start command, drop "not built yet"), `CLAUDE.md` (stack: `gradio`, `pydantic`, `uv` now in use; repo layout for `app/`; the profiles are in the config), `docs/roadmap/week-05.md` (tick what is done)
- [X] T062 Walk through quickstart.md sections 1 to 3 in the browser (scenarios A to E; A, B and D are paid, about $0.60, with the owner's go-ahead) and note the result of each in `specs/001-battlemap-tracer-app/quickstart.md` under a dated "Validation run" heading
- [ ] T063 **Owner's step.** Upload a `.dd2vtt` downloaded from the app to Roll20 (Page Menu -> Upload Background) and confirm fog of war follows the walls (SC-002, the week 5 milestone); record it in `docs/results.md`

---

## Dependencies & Execution Order

### Phase dependencies

- **Phase 1 Setup**: start here. T001 -> T002 -> T003 in order; T004 to T007 any time.
- **Phase 2 Foundational**: needs T003. T008 -> T009; T010, T012, T014, T016 are
  independent files; each test task follows its module; T018 is independent.
- **Phase 3 US1**: needs Phase 2.
- **Phase 4 US2**: needs US1 (it adds a button to the same page and a second profile to the same pass).
- **Phase 5 US3**: needs US1. Independent of US2 in the service and tracer; shares `app/main.py`.
- **Phase 6 US4**: needs US1; uses the deadline from US3 (T038) if present, and works without it.
- **Phase 7 US5**: needs US1 only.
- **Phase 8**: T054 to T056 need Phase 2 and T047 (for `--detect-size`); T058 onward need all stories.

### Within a story

- Tests first, failing; then models and functions; then the page.
- `app/main.py` is edited by T029, T033, T034, T040 to T043, T050 and T053: never in parallel.
- `app/service.py` is edited by T027, T030, T041, T049, T052; `app/tracer.py` by T024, T039,
  T048; `llm/agent.py` by T009, T038, T047: one at a time each.

### Parallel opportunities

- Phase 1: T004, T005, T006, T007 together.
- Phase 2: T010 + T011, T012 + T013, T014 + T015, T016 + T017 as four separate tracks.
- US1: T019 to T023 (tests) together; T025 and T026 together.
- After US1: US2, US3 and US5 touch different functions, but all edit `app/main.py`, so
  for one developer the priority order is also the simplest order.

### Parallel example: User Story 1

```text
Tests, all at once (different files):
  T019 fixtures + conftest      T020 tests/test_app_tracer.py
  T021 tests/test_app_exporter.py   T022 tests/test_app_render.py   T023 tests/test_app_service.py

Then implementation:
  T024 app/tracer.py   |   T025 app/exporter.py   |   T026 app/render.py
  T027 app/service.py  ->  T028 Gradio check  ->  T029 app/main.py  ->  T030
```

---

## Implementation Strategy

### MVP first (User Story 1)

1. Phase 1 (the `uv` image must pass the whole existing suite before anything else).
2. Phase 2.
3. Phase 3, then stop and try quickstart.md scenario A with a typed map size and the
   Roll20 import (T063 can be done here already).

### Incremental delivery

1. US1 -> a working fast pass and download (MVP).
2. US2 -> the deep pass.
3. US3 -> safe under failure; this is the point where the app is fit to demonstrate.
4. US4 -> the model works out the map size.
5. US5 -> free map-size correction.
6. Phase 8 -> measured, documented, checked in Roll20.

### Paid steps and who approves them

| Task | What | Estimated cost |
| --- | --- | --- |
| T058 | Reference evaluation, both profiles, four maps | about $1.40 (spent $1.63, plus $0.08 for a repeat) |
| T062 | Browser walkthrough, scenarios A, B, D | about $0.60 |

Every other task runs with the fake client and costs nothing.

---

## Notes

- 63 tasks: Setup 7, Foundational 11, US1 12, US2 4, US3 9, US4 7, US5 3, final phase 10.
- The task that carries the most risk is T003 (PyTorch from the CPU index under `uv`). Its
  fallback is to keep `pip`; nothing else depends on `uv`.
- T028 exists because the Gradio details in research.md R13 are marked "to verify", not known.
- The plan mentions a `.gitignore` exception for `data/reference/`; none is needed, because
  only `data/raw/` and `data/processed/` are ignored. T005 ignores `data/test/` instead.
