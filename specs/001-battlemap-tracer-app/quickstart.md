# Quickstart: Battlemap Tracer App

How to run the feature and prove it works. Commands describe the finished feature; the app
and the new flags do not exist until the tasks are done. Details live in
[contracts/](contracts/) and [data-model.md](data-model.md).

## Prerequisites

- Docker with Docker Compose (on Windows: WSL integration on in Docker Desktop).
- For anything that calls the model: an Anthropic API key in `.env` in the repo root
  (gitignored), and an internet connection.

```bash
ANTHROPIC_API_KEY=...
```

## 1. Build and run the free checks

No key needed; nothing here costs money.

```bash
docker compose build
docker compose run --rm app pytest
docker compose run --rm app ruff check .
docker compose run --rm app ruff format --check .
```

Expected: every test passes, including the first approach's tests on the new `uv` image;
`ruff` reports nothing.

## 2. Start the app

```bash
docker compose run --rm --service-ports app python -m app.main
```

Open `http://localhost:7860`. Expected before any upload: map size 25 x 25, "detect map
size from the image" on, "Suggest walls" and "Deeper examination" disabled, "Accept mask"
visible and disabled, the third-party notice beside the upload, and each pass button
showing its expected time and cost.

## 3. Validation scenarios

Paid steps are marked. The whole list costs about $0.60.

### A. Fast pass to a file (User Story 1) — paid, about $0.09

1. Upload `data/test/map-26x28.jpeg`. Type 26 and 28 as the map size.
2. Click "Suggest walls".
3. Expected: a progress line with elapsed time; then walls, portals and lights over the
   map in three colors; a status line with "Sonnet 5.5 (medium)", the time, the estimated
   cost and the model's note.
4. Choose `.dd2vtt`, click "Accept mask". Then choose `.uvtt` and accept again.
5. Expected: two downloads with the two extensions and the same content.
6. **Owner's step:** in Roll20, Page Menu -> Upload Background with the `.dd2vtt`. Fog of
   war follows the walls.

### B. Deeper examination (User Story 2) — paid, about $0.32

1. After A, click "Deeper examination".
2. Expected: the mask is replaced; the status line shows "Opus 5.5 (medium)" with its own
   time and cost. The button can be clicked again.

### C. Failures and running state (User Story 3) — free

1. Stop the app. Start it with the key removed from `.env`. Upload a map, click "Suggest
   walls". Expected: the "No API key is set up" message; no stack trace; the app still
   works.
2. Restore the key. Get a mask (or reuse A). Disconnect the network, click "Deeper
   examination". Expected: the "Couldn't reach the AI provider" message, and the earlier
   mask still on screen and downloadable.
3. Upload a `.gif` and a file over 20 MB. Expected: a clear message each time, and nothing
   sent out.
4. Type 0 or 201 as a map size. Expected: the range message; no pass starts.
5. The other failure kinds (refusal, limits, timeout, unreadable answer) are covered by
   `tests/test_app_tracer.py` and `tests/test_app_service.py` with the fake client.

### D. Map size worked out by the model (User Story 4) — paid, about $0.10 each

1. Upload a map with a visible grid (for example the image of `data/reference/dd04_a.dd2vtt`;
   `data/test/map-26x28.jpeg` has no grid lines) and leave the map size alone. Click "Suggest walls".
2. Expected: the fields show the size the model found, with "Detected from the image"; the
   option is now off.
3. Upload a map with no grid (for example `data/reference/dd04_d.dd2vtt`'s image). Click
   "Suggest walls".
4. Expected: the mask is shown on 25 x 25 with the "No grid was found" message.

### E. Correcting the map size (User Story 5) — free

1. With a mask on screen, change the map width or height.
2. Expected: the preview redraws at once over the same image features; no progress line,
   no cost. Accept the mask and check the file's `map_size` is the new one.

## 4. Reference evaluation — paid, owner's approval first

Scores the reference maps and checks the spec's thresholds (SC-003, SC-004, SC-009).
About $0.40 for the fast profile and $1.30 for the deep one over four maps (13.11 run: $0.34
and $1.29).

```bash
docker compose run --rm app python -m llm.run --reference --profile quick --detect-size
docker compose run --rm app python -m llm.run --reference --profile deep --detect-size
```

Each prints the map count and estimated cost and asks before the first call. Expected in
`runs/<timestamp>_<profile>/summary.csv`:

| Map | Fast pass | Deep pass |
| --- | --- | --- |
| `dd07_a` castle | wall boundary F1 at least 0.95 | wall boundary F1 at least 0.95; portal recall over 0.5 |
| `dd06_a` cave | no threshold | wall boundary F1 at least 0.85 |
| `dd04_a` tavern | no threshold yet: this run sets the baseline | same |
| `dd04_d` no grid | "no grid found" reported | same |
| Map size (the three with a grid) | right on each, or the 80% target is revised | not thresholded |

A single run slightly under a floor is repeated before it counts as a regression. Results
go into `docs/results.md` with the run name, cost and number of runs, and the expected
time and cost in the config are updated to what was measured.

## 5. Done

- Sections 1 to 3 pass.
- Section 4 is run once approved, and its results are recorded.
- The Roll20 import in A.6 is confirmed by the owner.

## Validation run (2026-11-13)

Driven over HTTP with `gradio_client` against the real app (`app.main.build_ui`, the same
handlers and model calls as the page), not by clicking in a browser: the layout, the legend
and the rendered colors still need a look by eye. Previews were saved and checked by eye.
Paid part: about $0.52 (A $0.05, B $0.25, D $0.16 run twice, because the first run's size
fields were lost in the output).

| Scenario | Result |
| --- | --- |
| 1. Build, tests, lint | Pass: image builds with uv; 260 tests; ruff clean (commit `136bc1f`) |
| A. Fast pass, typed 26 x 28 | Pass. "Working… N s" each second; Sonnet 5.5 (medium), 10 s, about $0.05, 17 walls, 0 portals, 2 lights, with the model's note (it says itself it found no doors). `.dd2vtt` and `.uvtt` byte-identical, `map_size` 26 x 28 |
| A.6 Roll20 import | Not done: owner's step (T063) |
| B. Deeper examination | Pass. Mask replaced; Opus 5.5 (medium), 53 s, about $0.25, 24 walls, 11 portals, 2 lights; preview shows walls, doors and both chandeliers in place |
| C.1 No key | Pass: "No API key is set up…", no stack trace, progress shown first |
| C.2 No network (container with no network, real key) | Pass: "Couldn't reach the AI provider…" |
| C.3 `.gif`, file over 20 MB | First run: both refused by Gradio itself, with its own wording, before the app's handler; nothing sent to the model. Fixed the same day: Gradio's type filter was dropped, and a `.gif` now gets "That file type isn't supported. Upload a PNG, JPEG or WebP image." (re-checked). Over 20 MB is still refused by Gradio's server limit first, on purpose (see contracts/ui.md) |
| C.4 Size 0 or 201 | Pass: range message; a pass click with 0 starts nothing |
| D. Map size from the image | `map-26x28.jpeg` (no grid lines drawn): "No grid was found…", traced on 25 x 25, option stays on. Correct for that image, but it is not a gridded map; detection on gridded maps is measured in docs/results.md (Opus 4 of 4). `dd04_d` image (no grid): "No grid was found…", correct |
| E. Map size change | Pass: 13 x 14 typed with a mask on screen, no pass, the download's `map_size` is 13 x 14 |
