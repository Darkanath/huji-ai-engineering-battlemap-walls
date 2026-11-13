# Plan: battlemap tracer app (Sonnet draft, Opus deep pass, accept and download)

## Context

The course staff allowed a large model in place of a trained one (13.11). The spike and the two
model comparisons (`docs/results.md`) showed that Claude can place walls, portals and lights
straight from the image, and the tracing pipeline already exists (`llm/`). Training is dropped.

The product is now an app: the user uploads a map, a default **Sonnet** model suggests a mask
(walls, portals, lights drawn over the map), the user can ask for a **deeper examination** that
re-traces the map with **Opus**, and an always-present **Accept** button hands over the result
as a `.dd2vtt` or `.uvtt` file.

Measured on the two labeled maps (v2 harness, one run each), so the two buttons have honest
expectations:

| | Sonnet 5.5 (default) | Opus 5.5 (deeper) |
| --- | --- | --- |
| Time per map | about 20 s | about 60 s |
| Cost per map | about $0.07 | about $0.27 |
| Wall boundary F1, castle / mine | 0.96 / 0.66 | 0.99 / 0.88 |
| Portals on the castle | none found | most found |

Sonnet is a fast, cheap first draft that is good on buildings and weak on caves and doors; the
deep pass is what fixes those. The app should say so next to the button.

## What already exists and is reused

- `llm/agent.py` `trace_map(image, map_size, cfg, client, views_dir)` -> `Trace` (answer,
  cost, time, the model's closing note). The whole tool loop; no change to its logic.
- `llm/views.py` `render_view(..., uvtt=...)`: draws an answer over the map (the "mask" preview).
- `postprocess/uvtt.py` `answer_to_uvtt`, `write_uvtt`: the file writer.
- `data/rasterize.py` `overlay`, `rasterize_mask`: the thick-mask preview used in evaluation.
- `llm/run.py`: batch runs and scoring, for the results table.
- `docker-compose.yml` already exposes port 7860 and reads `.env` for the API key.

## Changes

### 1. Two model profiles in the config
`llm/configs/claude.toml`: replace the single `[model]` table with two profiles.

```toml
[profiles.quick]   # the default suggestion
name = "claude-sonnet-5-5"
effort = "medium"
[profiles.deep]    # "deeper examination"
name = "claude-opus-5-5"
effort = "medium"
```

- `llm/agent.py`: `load_config(profile="quick")` returns the config with `cfg["model"]` set from
  the chosen profile, so `trace_map` and `_request` stay as they are.
- `llm/run.py`: add `--profile quick|deep` (default `quick`); `--model` and `--effort` still
  override. Fable 5.2 stays available through `--model`.

### 2. App logic, separate from the UI: `app/service.py`
Plain functions, testable with the fake client from `tests/test_llm_agent.py`:

- `prepare(image, squares_w, squares_h)`: validates the upload (`.png`, `.jpg`/`.jpeg`,
  `.webp`; squares at least 1), converts to RGB.
- `suggest(image, map_size, profile)`: calls `trace_map` with that profile, returns a
  `Suggestion` (answer, preview image, model name, seconds, estimated cost, the model's note,
  and a clear message if the loop stopped without an answer: refusal, limits, missing key).
- `preview(image, map_size, answer)`: the mask preview, using `rasterize.overlay` on
  `rasterize_mask(answer_to_uvtt(...))`.
- `export(image, map_size, answer, extension)`: writes the file to a temp folder and returns
  its path. The image is rescaled to **70 px per square** and embedded (JPEG, as in the Roll20
  import that already worked). `.dd2vtt` and `.uvtt` are the same JSON; only the extension
  differs.

### 3. Gradio UI: `app/main.py`
One page, Python only (`gr.Blocks`):

- **Inputs:** image upload; map width and height in squares, pre-filled 25 x 25.
- **Suggest walls** button: runs the `quick` profile (Sonnet), shows the preview, a status line
  (model, time, estimated cost) and the model's note about what it was unsure of.
- **Deeper examination** button: enabled once a suggestion exists; runs the `deep` profile
  (Opus) as a fresh trace and replaces the preview. Labeled with the expected time and cost.
- **Accept mask** button and a `.dd2vtt` / `.uvtt` choice: always visible, enabled whenever a
  mask is on screen; produces the download for the mask currently shown.
- State (`gr.State`): the prepared image, map size and the current answer. A new upload clears
  it.
- Start command: `docker compose run --rm --service-ports app python -m app.main`, served on
  `0.0.0.0:7860`.

### 4. Dependency
Add `gradio` to `pyproject.toml` (already listed in the CLAUDE.md stack) and rebuild the image.

### 5. Tests
- `tests/test_app_service.py`: with the fake client, `suggest` returns a preview and an
  answer; `suggest` with the `deep` profile requests the Opus model; a loop that ends without
  an answer gives an error message, not a crash; `export` writes a file that `load_uvtt` reads
  back, with `pixels_per_grid` 70 and the right `map_size`, for both extensions.
- `tests/test_llm_agent.py`: `load_config("quick")` and `load_config("deep")` pick the right
  models.
- No test drives the browser; the UI file only wires buttons to `app/service.py`.

### 6. Docs, rewritten around the new product
- `CLAUDE.md`: the core is the Claude tracer, not a U-Net. Remove the Colab and training
  constraints; keep Python only, images in, labels from `.dd2vtt` (now for evaluation), the 4
  classes, Docker. Add `llm/`, the two profiles, the API key in `.env`, and "ask before a paid
  run larger than a few maps".
- `docs/PLAN.md`: new overview, architecture (upload -> Sonnet draft -> optional Opus pass ->
  accept -> file), evaluation (Canny vs the frozen stage-1 U-Net vs Sonnet vs Opus), risks
  (API cost, network dependence in the demo, caves).
- `docs/roadmap/`: weeks 4-9 rewritten: app (this plan), full evaluation run, grid detection
  as a stretch, error analysis, slides.
- `README.md`: new description, status and quick start.
- `train/`, the synthetic generator and the Colab notebook stay in the repo untouched, as the
  record of the first approach and the source of the U-Net comparison row. No further work on
  them.

### 7. Commit
One commit for the pipeline built today (`llm/`, `postprocess/uvtt.py`, tests, compose,
`pyproject.toml`, `docs/results.md`), one for the app, one for the docs. `data/test/` (a
published third-party map) stays out of git.

## Out of scope for this plan
- (Grid auto-detection was out of scope here; it was brought into scope on 2026-11-13, done by the
  model as part of a pass; see `specs/001-battlemap-tracer-app/spec.md`.)
- Editing the mask by hand in the app.
- The full evaluation on all 34 real maps (about $2.50 on Sonnet plus $9 on Opus): a separate
  paid run, to be approved on its own.

## Verification
1. `docker compose build`, then `docker compose run --rm app pytest` and
   `ruff check . && ruff format --check .`: all green.
2. Start the app, open `http://localhost:7860`, upload `data/test/map-26x28.jpeg` with 26 x 28
   squares:
   - **Suggest walls** shows a Sonnet mask with time and cost (expected about $0.07).
   - **Deeper examination** replaces it with an Opus mask (expected about $0.27).
   - **Accept mask** downloads a `.dd2vtt`, and again as `.uvtt`.
3. Upload the downloaded file to Roll20 (Page Menu -> Upload Background) and check that fog of
   war follows the walls. This step is yours.
4. The two paid checks in step 2 cost about $0.35 in total.
