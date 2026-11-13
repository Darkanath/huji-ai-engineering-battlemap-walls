# Research: Battlemap Tracer App

Phase 0 of the plan. Each entry is a decision the plan rests on. There were no open
"NEEDS CLARIFICATION" items in the Technical Context; the research is about fitting the plan
description to the code and measurements that already exist.

Entries marked **Adjusted** differ from the plan description given with `/speckit-plan`.

---

## R1. How a pass talks to the model — **Adjusted**

- **Decision**: a pass is the existing multi-turn tool loop (`llm.agent.trace_map`): the
  model receives the whole map and its four quarters with a labeled square grid, may ask
  for closer crops, submits its answer through a strict tool schema, sees the answer drawn
  over the map, and may correct it. `app/tracer.py` wraps the loop behind one function with
  the same interface for both passes.
- **Rationale**: this is the harness every number in the spec comes from. The spike found
  that "one look at the full image is not precise enough to place doors", and tracer v1
  showed that models which did not zoom in missed cave walls and doors
  (`docs/results.md`). The spec's success thresholds (SC-003, SC-004) are floors under the
  v2 loop's scores. The description's requirements are still met: structured output comes
  back through a tool schema, is validated with Pydantic, and is returned as a
  `TraceResult` or a typed failure.
- **Alternatives considered**: a single request with the image and a JSON schema, as the
  description reads. Rejected: unmeasured, and the closest measured cases (models that
  answered after one look) scored far lower. It would also need a new coordinate scheme
  with no grid for the model to read positions from.

## R2. Coordinates: grid squares for the model, image fractions in the app

- **Decision**: the model keeps answering in grid squares (it reads them off the gridded
  views). `app/tracer.py` converts each answer to fractions of the image width and height
  (0..1) and the app stores only fractions. Arcs are turned into polylines before the
  conversion. The exporter converts fractions back to grid squares with the map size on
  screen.
- **Rationale**: gives FR-005 (a map-size change keeps the mask over the same image
  features, with no pass) with no re-tracing, as the description asks. Arcs must become
  polylines first because a circle in grid squares is not a circle after a rescale to
  non-square cells.
- **Detail that matters**: the views are drawn with one pixels-per-square value,
  `image.width / map_width`, on both axes. So `fx = x / map_width` and
  `fy = y * (image.width / map_width) / image.height`. Dividing `y` by the map height would
  be wrong whenever the entered size does not match the image's proportions.
- **Alternatives considered**: storing grid squares plus the map size they were traced at.
  Rejected: every reader would have to rescale, and the description asks for fractions.

## R3. Map size worked out by the model

- **Decision**: when the "detect map size" option is on, the pass starts with one extra
  model turn: `llm.agent.detect_map_size()`, on the model of the profile named in
  `[size_step]` of the config, which is Opus (`deep`) in both passes (revised 13.11, see
  "Measured" below). It sends the whole
  map (no overlay) plus the top and left edge strips at higher zoom, and the model answers
  through a strict tool, `report_map_size {grid_found, width, height}`. A found size inside
  1..200 is used for the trace and written to the fields. Otherwise the pass uses the size
  in the fields and reports "no grid found". Token usage and time are added to the same
  pass, so the status line and the cost limit cover it.
- **Rationale**: the owner decided the model does grid detection, inside a pass (spec
  FR-004 to FR-004c, constitution v1.2.0). A separate first turn keeps the measured tracing
  loop unchanged: it still starts with a known size and gridded views.
- **Measured (13.11, `docs/results.md`)**: on the three reference maps with a grid, Sonnet
  found the right size on 1 of 3 (the mine read as 18 x 18, the castle as 20 x 20) and Opus
  on 3 of 3, then on a fourth Opus run (castle repeat) as well; both reported "no grid" on
  the grid-less map. **The owner decided the size step runs on Opus in both passes.** It
  adds about $0.03 and a few seconds to the fast pass, and the fast pass's shown estimate
  includes it. A pass that uses two models is priced per response (`Trace.add_usage`).
- **Alternatives considered**: (a) trace on a grid-less image in fractions: rejected, it
  throws away the measured harness. (b) A local detector: rejected by the owner.
  (c) Always use the fast model for the size, even in a deep pass: cheaper, but measured
  at 1 of 3 right, under SC-009's 80%; rejected. (d) Each pass's own model: the fast pass
  then misses SC-009; replaced by Opus in both passes.

## R4. Two profiles in one config file

- **Decision**: `llm/configs/claude.toml` gets `[profiles.quick]` (`claude-sonnet-5-5`,
  effort `medium`) and `[profiles.deep]` (`claude-opus-5-5`, effort `medium`), each with a
  display label, a deadline, and the expected time and cost shown on its button.
  `llm.agent.load_config(profile)` returns the config with `cfg["model"]` set from the
  profile, so `trace_map` and `_request` are untouched. `app/config.py` validates the whole
  file into a Pydantic `Settings` object.
- **Rationale**: model and effort stay config values (constitution II), and the loop's
  code path is identical for both passes.
- **Alternatives considered**: separate config files per pass (duplication); environment
  variables for the model names (harder to show in the repo and the slides).

## R5. Pass deadlines — **Adjusted in the spec**

- **Decision**: 60 s for the fast pass and 180 s for the deep pass, as the description
  asks, as config values. The loop stops with a timeout failure when the deadline passes;
  each request gets the time that is left as its own timeout.
- **Rationale**: measured times are about 20 s (Sonnet) and 57 to 133 s (Opus; the slowest
  was the mine at high effort). 180 s covers every Opus run seen so far; the map-size turn
  adds a few seconds.
- **Spec change**: the spec's assumption of "5 minutes per pass" is replaced by these two
  values.
- **Risk**: an unusually large or complex map on the deep pass could hit 180 s. The message
  tells the user to try again; the value is one line in the config.

## R6. Failure kinds and messages

- **Decision**: every way a pass can end without a usable answer maps to one `FailureKind`,
  each with one plain-language message (table in [contracts/ui.md](contracts/ui.md)).
  Sources: stop reasons (`refusal`, `max_tokens`), SDK exceptions
  (`AuthenticationError`, `PermissionDeniedError`, `RateLimitError`, `APITimeoutError`,
  `APIConnectionError`, other `APIStatusError`), a missing key (checked before any
  request), the loop's own limits (turns, cost, deadline), an answer that fails validation
  or was never submitted, and a catch-all for anything else. No exception leaves
  `run_pass`.
- **Rationale**: FR-024 to FR-027 and SC-006. A typed result makes each case testable with
  the fake client.
- **Alternatives considered**: one generic "something went wrong" message: fails FR-024
  ("what happened and what the user can do").

## R7. Lights table — **Adjusted**

- **Decision**: a `[lights.small|medium|large]` table in the config with `range` (grid
  squares) and `intensity`. Values today: 8 / 12 / 16 and 1. The writer takes the table as
  a parameter. A test checks it equals `LIGHT_TIERS` in `data/rasterize.py`, which the
  label reader uses.
- **Rationale**: the Universal VTT `lights` entry has `range` and `intensity`, and no
  separate bright and dim radius; Roll20 derives those from `range` on import (checked by
  hand on 21.10). So "bright and dim radius" from the description cannot be written to the
  file and is not stored.
- **Alternatives considered**: keeping bright and dim in the config for display only:
  rejected, a second set of numbers that nothing uses.

## R8. Export

- **Decision**: `app/exporter.py` builds the file with `postprocess.uvtt.answer_to_uvtt`
  from grid-square coordinates computed from the fractions. The image is resized to
  `map_width * 70` by `map_height * 70` px and embedded as JPEG (quality 90).
  `.dd2vtt` and `.uvtt` are the same bytes under two names.
- **Rationale**: reuses the writer that already produced a working Roll20 import; 70 px per
  square is Roll20's default; JPEG is the project's storage format for map images and keeps
  a 25 x 25 map near 0.6 MB.
- **Alternatives considered**: embedding PNG (about 3 times larger, no benefit to Roll20).

## R9. Reference maps — **Adjusted**

- **Decision**: `data/reference/` holds four of the owner's own Dungeondraft exports,
  committed: `dd04_a` (tavern: the ordinary building), `dd06_a` (mine: the cave),
  `dd07_a` (castle), and `dd04_d` (the tavern exported with no grid, for the "no grid
  found" case). Files keep the `.dd2vtt` extension their tool wrote. A README names each
  map's role. `.gitignore` gets an exception for the folder.
- **Rationale**: the description asks for building, cave and castle. The two maps with
  measurements behind them are the castle and the mine; the spec calls the castle "the
  building map". The tavern is added as a plain building with no threshold until its first
  scored run. About 8 MB in git.
- **Not committed**: `data/test/map-26x28.jpeg`, a published third-party map (constitution
  III).

## R10. Evaluation command and run folder — **Adjusted**

- **Decision**: extend the existing `python -m llm.run` with `--reference`,
  `--profile quick|deep` and `--detect-size`. It writes to `runs/<timestamp>_<profile>/`
  (or `--run NAME`): per map the raw model responses (text and tool calls, no images), the
  answer, the file, a preview and the trace; and `summary.csv` with wall boundary F1,
  portal recall, class IoUs, map size right or wrong, cost and time. It prints the
  estimated cost and the number of maps before the first call.
- **Rationale**: the command, its resume behaviour and its scoring already exist and
  produced every tracer number in `docs/results.md`. `runs/` is the project's run folder
  (gitignored, mounted in Docker); the description's `data/runs/` would be a second one.
  Scoring reuses `data/rasterize.py` and `eval/metrics.py` (boundary F1 at 32 px per
  square, tolerance 0.1 square).
- **New metric**: `portal_recall` in `eval/metrics.py`: a labeled portal counts as found
  when a predicted portal's midpoint lies within 0.5 square of its midpoint, matched one to
  one. This makes "most castle doors" (SC-004) a number.

## R11. Dependency management with uv

- **Decision**: adopt `uv` as the description asks: dependencies and the dev group in
  `pyproject.toml`, a committed `uv.lock`, and `uv sync --frozen` in the Dockerfile. PyTorch
  and torchvision come from the CPU wheel index through an explicit `uv` index entry, so the
  image stays CPU-only.
- **Rationale**: a lockfile makes the graded project reproducible. The owner asked for it.
- **Cost and gate**: the Dockerfile is rewritten and PyTorch has to be declared for the
  first time. Done as the first task, alone, and accepted only when the full existing test
  suite passes on the new image.
- **Alternatives considered**: keep `pip` (no change, but no lockfile). If the CPU index
  setup proves troublesome, fall back to `pip` and record it; nothing else in the plan
  depends on `uv`.

## R12. Pydantic for domain models and config

- **Decision**: Pydantic v2 models for `app/domain.py` and `app/config.py`. The model's
  tool input is validated into them at the boundary in `app/tracer.py`. `llm/agent.py`
  keeps its `Trace` dataclass and plain config dict.
- **Rationale**: validation at the two places untrusted data enters (model output, config
  file), with the "unreadable response" failure falling out of a `ValidationError`.
  Leaving the loop's internals alone keeps the measured code unchanged.

## R13. The page: Gradio specifics

- **Decision**: one `gr.Blocks` page. Upload through a file component limited to the three
  image types, with the 20 MB limit enforced both by the server's upload limit and in
  `service.prepare()`. Session state in `gr.State`. A pass handler is a generator: it
  starts the pass in a worker thread and yields the elapsed time about once a second, with
  both pass buttons disabled until it finishes. "Accept mask" is a download button whose
  file is rebuilt whenever the mask, the map size or the extension changes, so it works
  while a pass is running. The session's temp folder is removed when the session ends.
- **To verify at implementation**: the exact names for the download button, the upload size
  limit, session-end cleanup and generator updates in the Gradio version that gets
  installed. These are checked against that version's documentation before coding the page;
  the service functions do not depend on them.
- **Alternatives considered**: a FastAPI backend with a separate front end: needs
  JavaScript or hand-written HTML, which the constitution rules out.

## R14. Late results and session isolation

- **Decision**: each session has a request token, replaced on every upload. A pass records
  the token when it starts and its result is applied only if the token is unchanged
  (FR-006). The worker thread is not killed; its result is dropped. Its cost was still
  spent, and the log line says so.
- **Rationale**: simple and testable without threads in the test (call `apply_result` with
  a stale token).

## R15. Logging

- **Decision**: standard-library `logging` with one JSON object per line: event, profile,
  model id, served-by, elapsed seconds, token counts, estimated cost, stop reason or
  failure kind, map size and its source. Never the image, the answer's coordinates or the
  key.
- **Rationale**: the description asks for structured logs; no new dependency is needed.

## R16. Tests without paid calls

- **Decision**: tracer tests replay recorded responses: JSON fixtures of real response
  content (tool calls and text, no images) loaded into the scripted fake client that
  `tests/test_llm_agent.py` already has. One golden-file test: a fixture `TraceResult`
  plus a small fixture image must produce a `.uvtt` byte-identical to a committed file.
- **Rationale**: constitution II and IV. Fixtures can be captured from the first approved
  reference run's `responses.json`.
- **Note for the golden file**: JPEG bytes can differ between Pillow versions, so the
  golden comparison covers the JSON with the `image` field compared by decoded size, and
  the lockfile pins Pillow.
