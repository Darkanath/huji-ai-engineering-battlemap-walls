# Battlemap Tracer Constitution

## Core Principles

### I. Python Only, on the Laptop, under Docker

- All code MUST be Python. The only other files allowed are the Dockerfile,
  `docker-compose.yml`, `pyproject.toml`/requirements, config files (YAML/TOML) and docs.
- There MUST be no JavaScript and no hand-written HTML. The UI is built with Gradio.
- Everything MUST run on the laptop's CPU under Docker Compose (Ubuntu 24.04 base image,
  Python 3.12 in a virtual environment). GPU and CUDA dependencies MUST NOT be added.
- Commands are run through Docker Compose, for example `docker compose run --rm app pytest`.
- Local first: the app, the data and every tool run on the laptop. The only traffic that
  leaves it is the model call, made with the project owner's API key. Cloud deployment is
  optional and MUST NOT be started before everything works locally and the owner asks for it.

**Rationale:** these are course constraints, and one language with one way to run it keeps a
solo project small enough to finish and easy to grade.

### II. Paid Calls Are Visible, Bounded and Approved

- Every user action that calls a paid model MUST show its expected time and cost before the
  click, and the actual time and estimated cost afterward.
- The UI MUST state that uploaded images are sent to a third-party model provider.
- Input MUST be validated (file type, file size, map size) before any paid call is made.
- The provider key MUST come from `.env` or equivalent operator configuration. It MUST NOT be
  committed, logged, shown in the UI or asked of the user.
- Automated tests MUST NOT make paid calls; they use a fake client.
- A paid run larger than a few maps (for example a full evaluation) MUST be approved by the
  project owner first, with its estimated cost stated.
- Model names, effort levels and prices MUST live in configuration (`llm/configs/`), not in
  code.

**Rationale:** the core of the product is a metered outside service. Cost and data flow that
the user cannot see are the main ways this project could do harm or overspend.

### III. Measured, Not Assumed

- Every claim about detection quality MUST come from a scored run: answers rasterized and
  scored with the project's metrics (pixel IoU, boundary F1 at 32 px per square) against
  labels.
- Labels MUST come only from `.dd2vtt` files. Code MUST NOT read or depend on
  `.dungeondraft_map` source files.
- Every predictor (each Claude profile; the Canny baseline and the stage-1 U-Net were scored
  the same way before their code was removed) MUST be scored the same way, and results MUST be recorded in `docs/results.md` with the command or
  run name that produced them, the cost, and the sample size.
- Known weaknesses of a comparison (one run per cell, leaks, small samples) MUST be written
  next to the numbers.
- A change that affects tracing (prompts, views, model, effort) MUST be re-scored on the
  labeled reference maps before it is called an improvement.
- There is no held-out test set (dropped 2026-11-13: the app is the deliverable). Published
  third-party maps are used only to try and demonstrate the app; they are never scored,
  redistributed or committed.

**Rationale:** the project's main decision (a large model in place of a trained one) was made
on measurements, and the presentation rests on them. Numbers without their method cannot be
defended.

### IV. Tested and Documented Code

- Every module that transforms data MUST have a pytest test.
- App logic MUST live apart from the UI (plain functions the tests can call); the UI file
  only wires controls to that logic. No test drives the browser.
- Every module, package `__init__.py`, function, test, fixture and nested helper MUST have a
  docstring, written with the code and not as a cleanup pass. The Dockerfile and compose file
  carry comments.
- Public functions MUST have type hints. Code MUST pass `ruff check` and `ruff format --check`.
- A failure in a model call (refusal, limit, missing key, network, timeout, unreadable
  response) MUST reach the user as a plain-language message and MUST have a test. The app
  MUST NOT crash or show a stack trace.

**Rationale:** this is a graded AI Engineering project, so the code is part of the
deliverable; and a paid, networked dependency fails often enough that its failures need the
same care as its successes.

### V. Simple, Scoped for One Person

- Prefer the simple, working, measured solution over the clever one.
- A dependency is added only in the change that first uses it, and only after the project
  owner agrees.
- Existing working code is reused before new code is written (`llm/`, `postprocess/uvtt.py`,
  `data/rasterize.py`).
- Scope MUST stay at what one person can finish by 2026-12-23. Out of scope unless this
  constitution is amended: hand-editing the mask,
  user accounts, storing uploads after the session, output formats other than Universal VTT,
  and further work on model training.
- The first approach's code (U-Net training, synthetic generator, Colab training notebook,
  Canny baseline) was removed on 2026-11-13. It lives in the git history (up to commit
  `7a5979d`); its results stay in `docs/results.md` as the comparison row.

**Rationale:** a solo project with a fixed presentation date fails by growing, not by being
too small.

## Domain and Data Constraints

- **Input:** an image only: `.png`, `.jpg`/`.jpeg`, `.webp`.
- **Output:** one Universal VTT file (`.dd2vtt` or `.uvtt`, same JSON). Coordinates are in
  grid squares. The embedded map image is written at 70 px per grid square (Roll20's default).
  Code MUST still read any `pixels_per_grid` value and accept any map size; the default map
  size is 25 x 25 squares.
- **Grid detection:** the vision model works out the map's size in squares as part of a
  pass the user started. It MUST NOT be a separate or automatic paid call, and its time and
  cost MUST be inside that pass's shown figures. The map size MUST stay editable, the entered
  size always wins over the detected one, and when no grid is found the pass uses the size in
  the fields and says so.
- **Four classes, fixed:** `0 = background`, `1 = wall`, `2 = portal`, `3 = light`. Doors and
  windows are one portal class; there is no door/window split. There is one light class;
  a light's range and intensity come from its size tier (small / medium / large) and a lookup
  table, never from a per-light estimate.
- **Labeling rules:** wall = blocks sight and movement (building walls, palisades, cave walls,
  cliffs). Portal = a door or window in a wall; an open gap with no door stays a gap.
  Furniture, counters, rugs, trees, boulders and water are not walls. Light = a lit light
  source drawn in the image. Full rules: `docs/labeling-rules.md`.
- **Models:** two profiles in configuration: a fast default (Sonnet) and a deep pass (Opus).
  Measured expectations for each are kept in `docs/results.md` and shown in the UI.
- **Maps:** no more real maps are made, except when testing needs one.
- **Storage:** map images and previews are JPEG (quality 90). Masks are always PNG. Datasets,
  runs and third-party test maps stay out of git.
- **Licensing:** only synthetic maps and maps the project owner made are used for anything
  beyond testing.

## Development Workflow and Quality Gates

- Read `docs/PLAN.md` and the current plan or spec before starting a piece of work. Features
  go through spec, plan and tasks under `specs/`.
- A change is done when: tests pass (`docker compose run --rm app pytest`), `ruff` is clean,
  new code is documented, and any quality claim is backed by an entry in `docs/results.md`.
- Seed everything that is random from configuration. Record each scored run's configuration
  with its results.
- Commit only when the project owner asks. Commits are small and by topic (pipeline, app,
  docs). Secrets, datasets, runs and third-party maps are never committed.
- Decisions made and committed in earlier sessions win over later edits made by other tools.
  A doc change that contradicts a committed decision is flagged and confirmed before it is
  followed.
- Steps only the project owner can do (importing into Roll20, approving paid runs) are named
  as theirs in plans and task lists.

## Governance

- This constitution wins over other project documents where they disagree. `CLAUDE.md` is
  the runtime guidance file for day-to-day development and MUST be kept consistent with it.
- **Amendments:** the project owner approves every amendment. An amendment states what
  changed and why, updates the version and the amended date, and updates `CLAUDE.md` and any
  spec or plan it affects in the same change.
- **Versioning:** semantic. MAJOR for removing or redefining a principle; MINOR for a new
  principle or section, or materially expanded guidance; PATCH for clarifications and wording.
- **Compliance:** every plan includes a constitution check before design and again before
  tasks. A plan that breaks a principle MUST say which one, why, and what simpler option was
  rejected; otherwise the plan is changed.

**Version**: 2.0.0 | **Ratified**: 2026-11-13 | **Last Amended**: 2026-11-13
