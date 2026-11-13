# Implementation Plan: Battlemap Tracer App

**Branch**: `001-battlemap-tracer-app` (spec folder name; git is on `main`, no branch was created) | **Date**: 2026-11-13 | **Spec**: [spec.md](spec.md)

**Input**: Feature specification from `/specs/001-battlemap-tracer-app/spec.md`, plus the
plan description given with `/speckit-plan` (stack, architecture, data and evaluation,
testing, non-functional).

## Summary

A one-page local web app. The user uploads a battlemap image; "Suggest walls" traces it with
a fast model, "Deeper examination" re-traces it with a stronger one, and "Accept mask"
downloads the mask on screen as a Universal VTT file for Roll20. The model also works out the
map size in squares inside the pass when the user has not typed one.

Technical approach: the app is a thin Gradio page over plain Python functions. Those functions
wrap the tracer that already exists and is measured (`llm/agent.py`, the tool loop with
gridded views) and the file writer (`postprocess/uvtt.py`). New code adds typed domain models
(Pydantic), two model profiles in config, typed failures with plain-language messages, the
map-size step, a user preview, the export at 70 px per square, and an opt-in evaluation run
over a small committed reference set.

The plan description was written without the repo in view in a few places (for example
"reuse the scoring logic from my earlier experiments, if present"). Where it differs from
what is built and measured, this plan keeps the built thing and says so:
[research.md](research.md) lists every such point (R1, R5, R9, R10, R11) with the reason.

## Technical Context

**Language/Version**: Python 3.12 (Ubuntu 24.04 default)

**Primary Dependencies**: `anthropic` 2.8 (installed), `Pillow`, `numpy`,
`opencv-python-headless` (installed; scoring). New: `gradio` (UI), `pydantic` v2 (domain
models and config). Tooling change: `uv` for dependency management with a lockfile. The
first approach's packages (PyTorch CPU, `segmentation_models_pytorch`, `albumentations`,
`mlflow`) stay installed for the frozen code and its tests.

**Storage**: none. Per-session state in memory plus a per-session temp folder for the export
file, deleted when the session ends. Evaluation runs write under `runs/` (gitignored).

**Testing**: `pytest`; recorded model responses and a scripted fake client, no paid calls.
`ruff check` and `ruff format --check`.

**Target Platform**: the owner's laptop (Intel CPU, no GPU), Docker Compose, Ubuntu 24.04
image, browser at `http://localhost:7860`.

**Project Type**: local single-user web app, plus a command-line evaluation tool.

**Performance Goals**: fast pass about 25 s and about $0.10 per map; deep pass about 70 s
and about $0.32 (measured 13.11 on the reference maps, including the map-size step on Opus;
first planned at 20 s / $0.07 and 60 s / $0.27 without it). Upload to download under 2 minutes with the fast pass (SC-001). Preview and export
after a map-size change in under 1 s, with no model call.

**Constraints**: Python only, no JavaScript or hand-written HTML. Nothing leaves the laptop
except model calls with the owner's key. No paid call in tests, none before input is
validated, none that the user did not start. Pass deadlines: 60 s fast, 180 s deep
(config). Uploads up to 20 MB; map size 1 to 200 squares each way. Key only from
`ANTHROPIC_API_KEY`; never logged or shown.

**Scale/Scope**: one user at a time; one page; about 8 new modules in `app/`, small changes
in `llm/`, `postprocess/` and `eval/`; 4 committed reference maps.

## Constitution Check

*GATE: Must pass before Phase 0 research. Re-check after Phase 1 design.*

Checked against constitution v1.3.0.

| Principle | Gate | Result |
| --- | --- | --- |
| I. Python only, on the laptop, under Docker | All new code is Python; UI is Gradio; runs under Docker Compose on the CPU image; no CUDA; only model calls leave the laptop | Pass. `uv.lock` is a requirements file, which the principle allows |
| II. Paid calls visible, bounded, approved | Expected time and cost on both buttons, actual in the status line; third-party notice at the upload; validation before any call; key from `.env`, never logged or shown; tests use a fake client; model names, effort and prices in config; evaluation run is opt-in and prints its estimated cost first | Pass |
| III. Measured, not assumed | The tracing loop is reused unchanged, so earlier scores stay comparable; every tracer change in this plan (map-size step, profiles) is re-scored on the reference maps before it is called good; results go to `docs/results.md` with run name, cost and sample size; third-party maps stay uncommitted | Pass |
| IV. Tested and documented code | App logic in plain functions apart from the UI; a test for every data-transforming module; every failure cause has a message and a test; docstrings on everything; `ruff` clean | Pass |
| V. Simple, scoped for one person | Reuses `llm/`, `postprocess/uvtt.py`, `data/rasterize.py`, `eval/metrics.py`; new dependencies `gradio` (agreed), `pydantic` and `uv` (asked for by the owner in the plan description); no out-of-scope item is built | Pass |
| Domain and Data Constraints | Four classes; one portal type; light `range` and `intensity` from a tier table; 70 px per square output; any map size accepted; map size worked out by the model inside a pass the user started, never a separate call; typed size wins | Pass |

No violations, so Complexity Tracking is empty.

**Re-check after Phase 1 design**: still passing. Two points to watch during implementation:

- Committing four reference maps (about 8 MB) adds real maps to git. They are the owner's
  own maps, so licensing is fine, and `data/reference/` needs a `.gitignore` exception.
- Moving the Docker image to `uv` touches the frozen first-approach stack (CPU-only PyTorch
  from its own index). The gate is the whole existing test suite passing on the new image.

## Project Structure

### Documentation (this feature)

```text
specs/001-battlemap-tracer-app/
├── plan.md              # This file
├── research.md          # Phase 0: decisions, and where the plan description was adjusted
├── data-model.md        # Phase 1: domain models, state, conversions
├── quickstart.md        # Phase 1: how to run and validate
├── contracts/
│   ├── ui.md            # The page: controls, states, messages
│   ├── service.md       # The functions the UI and the tests call
│   ├── export-file.md   # The Universal VTT file the app writes
│   └── config-and-cli.md  # Config tables and the evaluation command
├── checklists/requirements.md
└── tasks.md             # Phase 2 (/speckit-tasks), not created here
```

### Source Code (repository root)

```text
app/
├── __init__.py
├── config.py        # NEW  Settings (Pydantic): profiles, prices, limits, lights, app limits
├── domain.py        # NEW  Point, Wall, Portal, Light, MapSize, TraceResult (fractions 0..1)
├── errors.py        # NEW  FailureKind, PassFailure, the message for each kind
├── tracer.py        # NEW  run_pass(): map-size step + llm.agent.trace_map -> TraceResult or PassFailure
├── exporter.py      # NEW  TraceResult + map size + image -> Universal VTT dict, bytes, file
├── render.py        # NEW  overlay preview for the user (Pillow)
├── service.py       # NEW  Session state and the functions the UI calls
├── logging.py       # NEW  structured log lines (no image, no key)
└── main.py          # NEW  Gradio Blocks page; wiring only

llm/
├── agent.py         # CHANGED  load_config(profile); deadline; detect_map_size(); raw responses kept
├── views.py         # unchanged
├── run.py           # CHANGED  --profile, --reference, --detect-size, timestamped run folder, portal recall
└── configs/claude.toml  # CHANGED  [profiles.quick], [profiles.deep], [lights.*], [app]

postprocess/uvtt.py  # CHANGED  light table passed in (default LIGHT_TIERS); nothing else
eval/metrics.py      # CHANGED  portal_recall()
data/reference/      # NEW  dd04_a (tavern), dd06_a (cave), dd07_a (castle), dd04_d (no grid) + README

tests/
├── fixtures/        # NEW  recorded model responses (JSON), golden .uvtt, small images
├── test_app_config.py, test_app_domain.py, test_app_errors.py, test_app_tracer.py,
│   test_app_exporter.py, test_app_render.py, test_app_service.py, test_app_logging.py   # NEW
├── test_llm_agent.py      # CHANGED  profiles, map-size step, deadline
├── test_uvtt_writer.py    # CHANGED  light table parameter
├── test_metrics.py        # CHANGED  portal recall
└── (existing tests unchanged)

Dockerfile           # CHANGED  uv, lockfile install
pyproject.toml       # CHANGED  gradio, pydantic, torch under a CPU index for uv
uv.lock              # NEW
docker-compose.yml   # CHANGED  comment and app start command documented; data/reference mounted with data/
.gitignore           # CHANGED  keep data/reference/
```

**Structure Decision**: keep the repo's existing top-level packages (`llm/`, `postprocess/`,
`eval/`, `data/`, `app/`, `tests/`). The seven modules named in the plan description map
onto them as follows: domain -> `app/domain.py`; tracer -> `app/tracer.py` over
`llm/agent.py`; pricing -> `[prices]` in the config, read through `app/config.py`; lights ->
`[lights]` in the config; exporter -> `app/exporter.py` over `postprocess/uvtt.py`; render
-> `app/render.py`; app -> `app/service.py` (logic) and `app/main.py` (wiring). No `src/`
folder is introduced: the packages are already installable from the root.

## Design overview

Details are in [data-model.md](data-model.md) and [contracts/](contracts/). The shape:

1. **Upload** -> `service.prepare()` checks type, size and readability, opens the image,
   starts a fresh session (new request token, cleared mask and status). No model call.
2. **Pass** -> `service.start_pass(session, kind)` checks the map size (or that detection is
   on), then `tracer.run_pass()`:
   - map size not given: one extra model turn, `llm.agent.detect_map_size()`, in the same
     pass, on the `[size_step]` model (Opus, in both passes; revised 13.11 after the
     reference run); no grid found falls back to the size in the fields;
   - `llm.agent.trace_map()` runs the measured tool loop with a deadline;
   - the answer is validated and converted to a `TraceResult` in image fractions;
   - any error or bad stop becomes a `PassFailure` with a kind.
   The result is applied only if the session's request token is unchanged.
3. **Preview** -> `render.overlay()` draws the current `TraceResult` over the image.
4. **Map size change** -> preview and export are rebuilt from the same fractions; no call.
5. **Accept** -> `exporter.build()` writes grid-square coordinates from the fractions and the
   map size on screen, embeds the image at 70 px per square, and saves it under the session's
   temp folder with the chosen extension.

## Phase 2 preview: order of work (for /speckit-tasks)

1. **Tooling**: `uv` + lockfile in Docker; whole existing suite green on the new image.
2. **Foundations**: config (profiles, lights, app limits), domain models, failure kinds and
   messages, structured logging.
3. **US1 (P1)**: tracer wrapper with given map size, exporter, render, service, Gradio page:
   upload -> suggest -> accept. Golden-file test.
4. **US2 (P2)**: deep profile, button gating, the note.
5. **US3 (P3)**: progress with elapsed time, locking, every failure kind end to end,
   late-result drop.
6. **US4 (P4)**: map-size step in the pass, the option, fallback message.
7. **US5 (P5)**: map-size change rescales without a call.
8. **Evaluation**: reference set, portal recall, `llm.run --reference`; paid runs only after
   the owner approves, results into `docs/results.md`; update the expected time and cost.

## Complexity Tracking

No constitution violations to justify.
