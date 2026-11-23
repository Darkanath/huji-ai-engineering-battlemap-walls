# Battlemap Tracer

Course project (Hebrew University, AI Engineering). Upload a top-down battlemap image and get back a
Universal VTT file (`.dd2vtt` or `.uvtt`) with walls, portals and light sources placed, ready to
upload to Roll20 for dynamic lighting and fog of war.

The core is a **Claude wall tracer** (`llm/`): a large vision model reads the map image and
answers with walls, portals and lights in grid squares. The course staff allowed a large model in
place of a trained one on 2026-11-13, and the measurements in `docs/results.md` showed it beats
the trained U-Net. **Model training is dropped**, and the first approach's code (U-Net training,
synthetic generator, Colab training notebook, Canny baseline) was removed on 2026-11-13; it is
in the git history up to commit `7a5979d`, and its results stay in `docs/results.md`.

Where to look before starting a piece of work:

- `.specify/memory/constitution.md`: the project's principles. It wins over this file where they
  disagree.
- `specs/NNN-name/`: the spec, plan and tasks of each feature (current: `specs/001-battlemap-tracer-app/`).
- `docs/results.md`: every measurement. `docs/lessons.md`: what didn't work, for the slides.
- `docs/PLAN.md`: the project plan, rewritten around the tracer on 2026-11-13. `docs/history/`:
  the first approach's training notes, the old map specs, the app plan the spec grew from, and
  roadmap weeks 1-4 (the week-by-week roadmap for later weeks was dropped on 2026-11-23; the
  specs' task lists track the work).

Final presentation: 2026-12-23.

## Hard constraints (do not drift from these)

- **Python only.** All code is Python. The only non-Python files allowed are the Dockerfile,
  docker-compose.yml, pyproject/requirements, config files (YAML/TOML) and docs. No JavaScript or
  hand-written HTML; the UI is built with Gradio.
- **Images in.** Input is an image only: `.png`, `.jpg`/`.jpeg`, `.webp`.
- **Labels come only from .dd2vtt files**, and are now used for evaluation, not training. Never
  read or depend on `.dungeondraft_map` source files.
- **4 classes:** `0 = background`, `1 = wall`, `2 = portal` (doors and windows together; no
  door/window split, not even as a stretch goal), `3 = light` (a drawn light source: torch,
  candle, lantern, brazier, campfire, bonfire). One light class only; brightness comes from the
  light's **size tier** (small / medium / large) and a lookup table, never from a per-light
  estimate.
- **Runs on the laptop under Docker** (Intel CPU, no NVIDIA GPU), Ubuntu 24.04 base image, started
  with Docker Compose. No GPU or CUDA dependencies; nothing heavy runs locally (the model runs
  at Anthropic).
- **Paid model calls are visible and approved.**
  - The app shows each paid action's expected time and cost before the click, and the actual
    time and estimated cost after it.
  - The app says that uploaded images are sent to a third-party model provider.
  - Input is validated (type, size, map size) before any paid call.
  - Tests never make paid calls; they use the fake client in `tests/conftest.py`.
  - **Ask before a paid run larger than a few maps**, and state its estimated cost.
- **The API key lives in `.env`** (`ANTHROPIC_API_KEY`, gitignored, read by Docker Compose). Never
  commit, log or display it; the app never asks the user for it.
- **Grid detection is in scope, and the model does it.** As part of a pass the user started,
  the vision model works out the map's size in squares and the app fills it in, when the user
  ticks "Detect map size from the image" (off by default since 13.11: about $0.03 per pass,
  and unreliable on faint grids); the user can
  always change it, and a typed size wins. There is no local grid detector and no separate or
  automatic paid call for it. If no grid is found, the pass uses the size in the fields and says
  so.
- **Local first.** Everything runs on the laptop; the only thing that leaves it is the model call,
  made with the owner's API key. Cloud deployment is optional and not to be started until
  everything works locally and the owner asks for it.
- **No more real maps.** The maps not yet made (`dd09`-`dd13`, `da02`-`da06`) are dropped; a new
  map is made only if testing needs one.
- Solo project. Keep the scope at what one person can finish by 2026-12-23.

## Stack

- Python 3.12 (Ubuntu 24.04 default), in a virtual environment inside the container (PEP 668).
- In use: `anthropic` (Claude API), `gradio` (UI), `pydantic` v2 (domain models and config),
  `numpy`, `Pillow`, `opencv-python-headless` (boundary F1), `pytest`, `ruff`. The first
  approach's PyTorch, `segmentation_models_pytorch`, `albumentations` and `mlflow` were removed
  on 2026-11-13.
- Dependencies are managed with `uv`: declared in `pyproject.toml`, locked in `uv.lock`,
  installed with `uv sync --frozen` in the Dockerfile. After changing one, run `uv lock` and rebuild the image.
- Agreed but not yet installed: `shapely` (visibility IoU, a stretch metric).
  Add a package only in the change that first uses it, and ask before adding anything not
  listed here.

## Models

Two profiles in `llm/configs/claude.toml`, measured on the reference maps with the v2 harness
and the map-size step (one to three runs per map; `docs/results.md`, 13.11):

| Profile | Model | Time per map | Cost per map | Wall boundary F1, castle / mine |
| --- | --- | --- | --- | --- |
| `quick` (default, "Suggest walls") | `claude-sonnet-5-5`, medium effort | about 25 s | about $0.10 | 0.91–0.97 / 0.55–0.66 |
| `deep` ("Deeper examination") | `claude-opus-5-5`, medium effort | about 70 s | about $0.32 | 0.99 / 0.88–0.89 |

- The fast pass is good on buildings and weak on caves and doors; the deep pass fixes most of that.
- `claude-fable-5-2` is the most accurate and the most expensive; it stays available through
  `--model` for comparisons.
- Model names, effort, limits and prices live in the config, never in code.
- The config has `[profiles.quick]` and `[profiles.deep]` (model, effort, deadline, expected
  time and cost shown on the buttons), `[lights.*]` and `[app]`; `app/config.py` validates it.
  `[size_step]` names the profile whose model works out the map size: `deep` (Opus) in both
  passes, because Sonnet got it right on 1 of 3 grid maps and Opus on 3 of 3. Re-measure with
  `python -m llm.run --reference --detect-size` (paid, ask first).
- **Chunked pass** (built 23.11, `specs/002-chunked-map-tracing/`; constitution 2.1.0): the map is
  split into up to 4 x 4 overlapping chunks, each traced by its own agent at the same time; the
  answers are merged by fixed rules, then an orchestrator model reviews only the strips along
  the borders between chunks. A selector next to the button picks the agents' model: Haiku,
  Sonnet (default) or Opus. The orchestrator model follows from it: Sonnet for Haiku or Sonnet
  agents, Opus for Opus agents. This is the only place Haiku is offered in the app. Its
  expected time and cost are estimates, marked as such in the config, until measured with
  `python -m llm.run --reference --chunked` (paid, ask first) and recorded in `docs/results.md`.

## Repo layout

```
llm/             Claude wall tracer: agent.py (tool loop, trace_map; with a window it is one
                 chunk agent), views.py (grid views and answer overlay), run.py (batch runs and
                 scoring, --chunked), configs/claude.toml. The chunked pass: orchestrator.py
                 (layout, parallel agents, trace_chunks), merge.py (rule-based merge, seams,
                 apply_review, seam_checks), review.py (the orchestrator model's seam review)
postprocess/     uvtt.py: the tracer's answer -> .dd2vtt / .uvtt (answer_to_uvtt, write_uvtt)
app/             Gradio app: service.py (logic, testable), main.py (UI wiring only),
                 tracer.py (run_pass: the only model call), exporter.py, render.py, progress.py
                 (live chunk board), domain.py
                 (Pydantic models, fractions <-> grid squares), config.py, errors.py, logging.py
eval/            metrics.py: pixel IoU, wall boundary F1, portal recall
data/            rasterize.py (.dd2vtt -> mask, LIGHT_TIERS), manifest.py, retier_lights.py +
                 configs/light_sources.toml (Dungeon Alchemist lights -> tiers)
  raw/           source .dd2vtt files (dungeondraft/, dungeon_alchemist/)
                 [gitignored]; Dungeon Alchemist exports keep their originals in original/
  processed/     image + mask pairs, manifest.csv                          [gitignored]
  reference/     dd04_a, dd06_a, dd07_a, dd04_d: the tracer's reference maps   [committed]
  test/          published third-party maps, for trying the app only       [never committed]
notebooks/       eda.ipynb: data exploration for the Data slide (runs on Colab)
specs/           feature specs, plans and tasks (Spec Kit)
docs/            PLAN.md, results.md, lessons.md, labeling rules, map log, history/
runs/            run outputs, answers, previews, scores                    [gitignored]
tests/           pytest
```

Datasets and runs are mounted as Docker volumes so they persist on the host.

## Universal VTT (.dd2vtt / .uvtt) facts

- One JSON file; `.dd2vtt` and `.uvtt` are the same content under two extensions. All coordinates
  are in **grid squares**, not pixels.
- `resolution.pixels_per_grid`, `resolution.map_origin`, `resolution.map_size`. Use **70 px per
  square**, Roll20's default: export Dungeondraft maps with the Roll20 grid preset, and write the
  output image at 70 px per square so Roll20 places it at native scale. Code must still read any
  `pixels_per_grid` value.
- `line_of_sight`: list of polylines (lists of `{x, y}`); these are the walls.
- `objects_line_of_sight`: extra sight blockers; treat as walls.
- `portals`: each has `position`, `bounds` (2 endpoints), `rotation`, `closed`, `freestanding`.
  No door/window type.
- `lights`: each has `position`, `range` (grid squares), `intensity`, `color`, `shadows`. Labels
  read `position` and map `range` to a size tier; the output writes one light per detected light,
  with `range` from the tier table (`LIGHT_TIERS` in `data/rasterize.py`: small 8, medium 12,
  large 16 squares).
- `image`: base64-encoded image of the map. **In a label file, this embedded image is the source
  of truth.** A same-named `.png` next to a `.dd2vtt` in `data/raw/` is optional: use it only for
  viewing, and if code reads it, first check its size matches `map_size` x `pixels_per_grid`.
- Roll20 accepts the file directly via Page Menu -> Upload Background.

## Pipeline conventions

- **Tracing:** the model gets the whole map plus its four quarters at higher zoom up front, each
  with a labeled square grid; it can ask for closer crops; it submits walls (polylines and arcs),
  portals and lights in grid squares, and sees its answer drawn over the map before it finishes.
  Limits per map (turns, views, submissions, cost) are in the config.
- **Chunked tracing:** the map is split into equal cores of the agents' model's part size
  (Haiku about 7 squares, Sonnet and Opus about 13; at most 4 x 4 parts; 4 agents at a time),
  each traced by its own agent on its core plus a 1-square margin; inner borders sit at
  quarter squares, off the grid lines walls are drawn on; the answers are merged by core
  ownership (each chunk keeps what lies in its own core), a wall drawn along a seam by both
  sides is kept once, wall ends are paired one to one across each seam and joined, then the orchestrator model rewrites only the strips 1 square either side of each
  seam. A test cuts real labels into chunks and merges them back with no loss (boundary
  F1 >= 0.99). `trace_map` without a window must send exactly what it always sent
  (`tests/fixtures/request_single_session.json`).
- **Default map size: 25x25 squares** (1750x1750 px at 70 px per square). The app pre-fills it,
  replaces it with the size the model works out during a pass, and the user can change it. Code
  must accept any map size.
- **Changing the map size** after a suggestion keeps the mask over the same image features; it
  does not run a pass.
- **Evaluation:** answers are rasterized with `data/rasterize.py` and scored with
  `eval/metrics.py` at **32 px per square** (boundary F1 tolerance 0.1 square), the same way for
  every predictor (the Canny and U-Net rows from the first approach were scored this way too).
  Results go in
  `docs/results.md` with the run name, cost and sample size.
- **Storage formats:** map images and previews are JPEG (quality 90). Masks are **always PNG**:
  JPEG is lossy and would corrupt class ids.
- **Real maps** = Dungeondraft (`ddNN`) + Dungeon Alchemist (`daNN`), both made by the user and
  labeled from their export. All style exports of one layout (`dd01_a`..`dd01_d`) stay in the
  same split. There is no held-out test set (dropped 13.11): the app is the deliverable.
- Labeling rules: wall = blocks sight and movement (building walls, palisades, cave walls,
  cliffs). Portal = door or window in a wall. An open gap with no door is just a gap. Furniture,
  counters, rugs, trees, boulders and water are not walls. Light = a lit light source drawn in the
  image; its tier is set by its `range` in the .dd2vtt (see `docs/labeling-rules.md`).
- Lights in a label mask: a disc at the light's `position`, radius by tier (0.25 / 0.40 / 0.60
  squares), drawn **under** walls and portals so a wall-mounted torch never cuts a gap in a wall.
- Data licensing: published third-party maps are used only to try and demo the app; they are
  never scored, redistributed or committed.

## Working conventions

- Type hints, small functions. **Docstrings on everything**: modules, package `__init__.py`
  files, every function including tests, fixtures and nested helpers; comments in the Dockerfile
  and compose file. The code is part of the graded deliverable.
- Format and lint with `ruff`.
- Every module that transforms data gets a pytest test, using the demo map in `data/raw/dungeondraft/`.
- App logic lives in plain functions apart from the UI, so tests can call it; no test drives the
  browser.
- A failed model call (refusal, limit, missing key, network, timeout, unreadable response) reaches
  the user as a plain-language message, never a crash or a stack trace, and has a test.
- Seed everything that is random from config; record each scored run's config with its results.
- Run everything through Docker Compose, e.g. `docker compose run --rm app pytest`. The app:
  `docker compose run --rm --service-ports app python -m app.main`, served on port 7860.
- Commit only when asked; small commits by topic. Decisions committed in earlier sessions win
  over later edits made by other tools.
- Prefer simple, working, measured solutions over clever ones. Ask before adding a new dependency.
