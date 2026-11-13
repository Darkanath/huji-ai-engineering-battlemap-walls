# Battlemap Tracer — Project Plan

Oct 20, 2026 · @Tal · rewritten 13.11.2026 around the Claude tracer

## Overview

Upload a battlemap image, get back a Universal VTT file (`.dd2vtt` or `.uvtt`) with walls, portals (doors and windows) and light sources already placed, ready to drop into Roll20. The core is a **Claude wall tracer**: a large vision model reads the map image and answers with walls, portals and lights in grid squares, which a small writer turns into the file.

**Why it matters:** tracing walls by hand for dynamic lighting takes a GM 20–30 minutes per map. Existing tools (Auto-Wall, Dungeon Channel) use classical edge or color detection and struggle with textured maps and furniture. A model that understands the picture can tell a wall from a table.

**What changed on 13.11.** The plan until then was a U-Net trained on synthetic maps and fine-tuned on real ones. On 13.11 the course staff allowed a large model in place of a trained one. A spike and two model comparisons the same day ([results.md](results.md)) showed Claude placing walls, portals and lights straight from the image, well ahead of the stage-1 U-Net and the Canny baseline on the two maps tried. Training stopped there. What was built for it stays in the repo as the record of the first approach (see "First approach" below) and supplies two rows of the final comparison.

**Final presentation:** 23.12.2026 (session 33).

**Success criteria:**

- The tracer beats the Canny baseline and the stage-1 U-Net on the real maps, scored the same way.
- A Dungeondraft- or Dungeon Alchemist-style building map produces a file that imports into Roll20 with fog of war following the walls and no manual fixes; a cave map needs at most a few minutes of fixes.
- A working web app: upload, fast suggestion, optional deeper examination, accept, download. Every paid action shows its expected time and cost before the click.
- An honest error analysis, including where the tracer fails (caves, outdoor and photoreal maps) and what it costs per map.
- The first approach is shown too: what was trained, how it was validated, and why it was dropped.

The feature-level requirements and measurable targets are in [`specs/001-battlemap-tracer-app/spec.md`](../specs/001-battlemap-tracer-app/spec.md); the project's rules are in [`.specify/memory/constitution.md`](../.specify/memory/constitution.md).

## Course requirements

From the course brief (`Graduation Project.pdf`, received 26.10).

- An end-to-end AI/ML system on **real data** that solves a practical problem, with a working demo.
- The brief's core challenge was to train a model. **13.11: the course staff allowed a large model in place of a trained one.** The project keeps its trained U-Net (stage 1) as a measured comparison.
- Teams of up to 3; this project is solo.
- Start data collection, **cleaning and EDA** early, and refine the goal from what the data shows (see Data cleaning & EDA).
- Plan milestones for data, modeling, evaluation and presentation (Timeline).
- **Final presentation: up to 12 minutes, no code.** Suggested structure: title, motivation, problem definition, literature / related work, data (source, size, key properties, cleansing techniques), methodology, results and conclusions, limitations and future work. Share what worked, what worked best and **what didn't work** (kept in `docs/lessons.md`).
- **Submission (confirmed 26.10):** the presentation itself (up to 12 minutes, given by me), a live demo and the code repository.

## Scope

The app targets indoor, top-down maps in a Dungeondraft-like or Dungeon Alchemist-like style. Caves work with the deep pass. Other styles are reported as a limitation.

|  | In | Out or stretch |
| --- | --- | --- |
| Map types | Indoor dungeons, buildings, taverns, caves | Outdoor and photoreal maps: tried in the app, not scored |
| Classes | Background, wall, portal (doors and windows together), light (one class; brightness from a size tier) | Sight-blocking objects like pillars; light color, flicker, per-light brightness |
| Grid | The model works out the map size in squares during a pass; the user can always type it, and a typed size wins | Hex and isometric grids; a separate local grid detector |
| Multi-floor images | User crops each floor before upload | Automatic floor splitting |
| Output | `.dd2vtt` / `.uvtt` with walls, portals, lights, embedded image at 70 px per square | Other formats; native Roll20 API integration; VTTs other than Roll20 as a tested target |
| App | Fast pass, deep pass, accept and download; clear messages on failure | Editing the mask by hand; undo; accounts; keeping uploads after the session |
| Never | Traps and secret doors (not visible in the image by design) |  |

## System architecture

One pipeline, run once per uploaded map:

1. **Upload and check.** The image type, file size and map size are validated before anything is sent out.
2. **Views.** The map is drawn with a labeled square grid: the whole map plus its four quarters at higher zoom (`llm/views.py`).
3. **Trace.** Claude receives the views, can ask for closer crops, and submits walls (polylines and arcs), portals and lights in grid squares. Each submission is drawn over the map and shown back to the model, which can correct it (`llm/agent.py`, `trace_map`). Limits on turns, views, submissions and cost per map are in `llm/configs/claude.toml`.
4. **Map size.** When the user has not typed one, the model also works out the map's size in squares in the same pass.
5. **Preview.** The answer is drawn over the map for the user (walls, portals and lights, each distinct).
6. **Write.** On accept, the answer becomes a Universal VTT file with the image embedded at 70 px per square (`postprocess/uvtt.py`).

**Two profiles** share this pipeline:

| Profile | Model | Time per map | Cost per map | Wall boundary F1, castle / mine | Portals on the castle |
| --- | --- | --- | --- | --- | --- |
| `quick`: "Suggest walls" | Sonnet 5.5, medium effort | about 25 s | about $0.10 | 0.91–0.97 / 0.55–0.66 | none found |
| `deep`: "Deeper examination" | Opus 5.5, medium effort | about 70 s | about $0.32 | 0.99 / 0.88–0.89 | most found (0.94 recall) |

Measured on the reference maps with the map-size step, one to three runs per map (v2 harness, [results.md](results.md), 13.11). The map size is worked out by Opus in both passes. The fast pass is a cheap first draft, good on buildings and weak on caves and doors; the deep pass is what fixes those. The app says so next to the button.

The `.dd2vtt` rasterizer (`data/rasterize.py`) is shared by evaluation: it turns both a label file and a model's answer into class masks, so every predictor is scored the same way.

## Data

The data is now used for **evaluation**, not training. Nothing is sent to the model except the image being traced.

| Dataset | Size | Labels come from | Used for |
| --- | --- | --- | --- |
| Dungeondraft | 8 layouts × 4 style variants (`dd01`–`dd08`), 32 maps | The .dd2vtt export (exact) | Evaluation of every predictor |
| Dungeon Alchemist | 1 layout, 2 variants so far (`da01`) | The .dd2vtt export, light ranges mapped to tiers | Evaluation |
| Third-party maps | A few published maps | Not labeled | Trying and demoing the app only; never scored or committed (test set dropped 13.11) |
| Synthetic | 500 maps, generated by script | The generator itself (exact) | First approach only: trained the stage-1 U-Net |

- **No more real maps are needed (decided 13.11).** `dd09`–`dd13` and `da02`–`da06` ([map-specs.md](history/map-specs.md)) were planned as training data and are dropped. A new map is made only if testing needs one.
- **Development maps.** The tracer's prompt and views were tuned while looking at `dd06` (mine) and `dd07` (castle). Their scores are reported separately from the other layouts, the way a validation score is kept apart from a test score.
- **Decided (20.10): inputs are images only (.png, .jpg, .webp); labels come only from the .dd2vtt.** The `.dungeondraft_map` source file is never used.
- **Decided (21.10): one portal class.** The .dd2vtt `portals` carry no door/window type. Roll20 imports every portal as a door, and the GM flips the few windows by hand.
- **Decided (21.10): light sources are a 4th class with a size tier.** Brightness cannot be read from the image (the same torch sprite could be 20 ft or 40 ft of light). Each light gets a tier (small: candle, torch; medium: lantern, brazier, campfire; large: bonfire); the model names the tier and a lookup table gives the range (`LIGHT_TIERS` in `data/rasterize.py`: 8 / 12 / 16 squares). In a label mask a light is a disc of 0.25 / 0.40 / 0.60 squares, drawn under the walls.
- **Dungeon Alchemist** light ranges are set per asset type, not by tier, so `data/retier_lights.py` maps them to tiers from a rules table (`data/configs/light_sources.toml`) and keeps the original export untouched.

### Data cleaning & EDA

- **Cleaning (per map, before the manifest):** walls and portals line up with the image (rasterizer preview overlay); embedded image size = `map_size` × `pixels_per_grid`; light `range` matches a tier (the rasterizer stops otherwise); stacked duplicate lights merged; stacked or duplicate portals flagged (as in `dd01`); `objects_line_of_sight` from stray object shadows checked; Dungeon Alchemist lights re-tiered with the original kept. Every map dropped or fixed is noted in `map-log.md` with the reason.
- **EDA** (`notebooks/eda.ipynb`, run 26.10; summary in [results.md](results.md)): maps and layouts per dataset, class pixel shares, wall thickness and portal width in squares, lights per tier, and how far apart synthetic, Dungeondraft and Dungeon Alchemist maps are. Its figures go into the Data slide.

### Labeling rules

Full rules: [labeling-rules.md](labeling-rules.md). The same rules are given to the tracer in its prompt.

- **Wall** = anything that blocks both sight and movement: building walls, palisades, cave walls, cliff faces.
- **Door** = a gap in a wall with a door drawn in. An open archway is just a gap, no portal.
- **Window** = see-through barrier in a wall. Doors and windows both get the one portal class.
- **Not walls:** furniture, counters, rugs, trees, boulders, water.
- **Light** = a lit light source drawn in the image (flame or lamp visible), with a size tier. Unlit fixtures and glow without a source are background.

### Licensing and privacy

- Maps made for this project (Dungeondraft, Dungeon Alchemist) and synthetic maps are the only ones used beyond testing. Published maps (e.g. Red Raspus) are used only to try and demo the app; they are never scored, redistributed or committed, and are cited in the report.
- Every traced image is sent to a third-party model provider (Anthropic). The app says so where the user uploads. The API key comes from the operator's `.env`; the user never enters one.

## Related work

For the literature slide; one line each, filled in during week 8.

- **VTT wall tools:** Auto-Wall and Dungeon Channel (classical edge and color detection; the Canny baseline here copies their approach). Foundry's and Roll20's own tools need walls drawn by hand.
- **Floor-plan parsing:** the closest research area. Raster-to-vector floor-plan conversion and the CubiCasa5k dataset use segmentation followed by vectorization, the two stages of the first approach.
- **Segmentation models:** U-Net and pretrained encoders for thin structures; Dice and focal loss for rare classes (first approach).
- **Vision-language models on spatial tasks:** large models reading diagrams and plans with tool use (asking for crops, checking their own answer on an overlay), the approach the tracer uses.
- **Synthetic-to-real transfer:** pretraining on generated data, then fine-tuning on a small real set (first approach; the gap it left is in results.md).

## The tracer: what was tried

All measured on `dd07_a` (castle) and `dd06_a` (mine); numbers and costs in [results.md](results.md).

1. **Spike (13.11).** Claude inside a working session, looking at the full image, four gridded quarters and a few close-ups: wall boundary F1 0.995 and 0.957. One look at the full image was not enough to place doors.
2. **Tracer v1.** The same idea as an API pipeline, with the model choosing when to zoom in. Only Opus was usable; Sonnet and Haiku answered almost without zooming and missed the cave walls. High effort did not beat medium.
3. **Tracer v2.** The four quarters are sent up front, so close reading no longer depends on the model asking. Every model improved: Opus portal IoU on the castle went from 0.25 to 0.70, Sonnet's cave boundary F1 doubled.
4. **Model choice.** Fable 5.2 is the most accurate and the most expensive. Opus 5.5 is close on walls for about 60% of the cost, so it is the deep pass. Sonnet 5.5 is about four times cheaper and three times faster, so it is the default draft.

Open points for the tracer: caves stay the weak spot for the fast pass (Sonnet never asks for a closer view); the fast pass finds almost no doors on buildings; most results are one run per cell, and three fast runs on the castle spread from 0.91 to 0.97 boundary F1. The map size is worked out by Opus in both passes: right on 4 of 4 runs on maps with a grid, and "no grid" on the grid-less map (results.md, 13.11).

## First approach (20.10–9.11): trained U-Net

The first approach's code (`train/`, the synthetic generator, the Colab training notebook, the Canny baseline) was removed from the repo on 13.11; it is in the git history up to commit `7a5979d`. Its results stay in [results.md](results.md); how it was trained is in [history/training.md](history/training.md).

- **Synthetic generator:** rooms-and-corridors and building layouts on a 25×25 grid, procedural textures, doors, windows, lights of all tiers, furniture as distractors, doorless gaps. 500 maps, each saved with its image, .dd2vtt, mask and seed, listed in the manifest.
- **Model:** U-Net with a pretrained ResNet-18 encoder, 4 classes, 256×256 crops at 32 px per square, cross-entropy + Dice with class weights. Trained on a Colab GPU; everything else on the laptop CPU.
- **Stage 1 (R1, 26.10):** synthetic only. On synthetic validation: wall IoU 0.90, boundary F1 0.996. On real validation (`dd03`): wall IoU 0.52, boundary F1 0.84, about level with Canny on boundary F1 but able to find portals.
- **What it showed:** a clear synthetic-to-real gap. Real-validation boundary F1 plateaued while the training loss kept falling.
- **Not done:** stage 2 (fine-tuning on real maps), the ablations, mask-to-polyline post-processing, ONNX export. The comparison with the tracer is therefore not a fair fight for the U-Net, and the presentation says so.

## Evaluation

The headline result: the tracer (both profiles) against the Canny baseline and the stage-1 U-Net, on the same maps, scored the same way.

| Level | Metric | What it tells you | Status |
| --- | --- | --- | --- |
| Pixel | IoU per class | Standard segmentation quality | Built |
| Boundary | Wall F1 with a tolerance of 0.1 square | Fair to thin structures; a wall 2 px off is not wrong. The main wall metric | Built |
| Map size | Share of maps whose size the model gets exactly right | Whether the user can skip counting squares | To build with the app |
| Cost | Estimated cost and time per map | What a suggestion costs | Built (run log) |
| Practical | Minutes of manual fixing in Roll20 per map | What a GM actually saves | By hand, weeks 6–8 |
| Gameplay *(stretch)* | Visibility IoU: ~100 viewpoints per map, visibility polygon with predicted vs true walls | Whether fog of war behaves correctly | Not built |
| Objects *(stretch)* | Light F1 (match within 0.5 squares) and tier accuracy | Whether lights are found and sized right | Not built |

- **How answers are scored:** the tracer's answer is written as a .dd2vtt, rasterized like a label, and compared at 32 px per square. Wall IoU is harsh on a hand-traced cave line that sits a fraction of a wall width off the label; boundary F1 is the fair metric there.
- **Baseline:** Canny edges + contours, the approach Auto-Wall uses. Retune its thresholds once on the real maps, then freeze it. It predicts no portals and no lights.
- **No further evaluation runs (decided 13.11):** the reference-map runs of both profiles, the tracer model comparisons and the week 2–3 Canny and U-Net results are the evaluation. The presentation's table is built from them, with their sample sizes stated.
- **No test set (decided 13.11):** the app is the deliverable, so the held-out set of hand-traced published maps is dropped.
- **Reporting:** development maps (`dd06`, `dd07`) apart from the rest; buildings apart from caves. A gallery of failure cases with a sentence on each. Every table states how many runs are behind each cell.

### Results: table to fill in

| Predictor | Wall IoU | Wall boundary F1 | Portal IoU | Light IoU | Map size right | Cost / map | Time / map | Fix time (min/map) |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| Canny baseline |  |  | 0 | 0 | - | 0 |  |  |
| U-Net, synthetic only (R1) |  |  |  |  | - | 0 |  |  |
| Claude tracer, `quick` (Sonnet 5.5) |  |  |  |  |  |  |  |  |
| Claude tracer, `deep` (Opus 5.5) |  |  |  |  |  |  |  |  |

## Application

One page, Python only (Gradio). Full behaviour: the spec; build plan: `specs/001-battlemap-tracer-app/` (it grew from [history/app-plan.md](history/app-plan.md)).

- **Upload** an image (`.png`, `.jpg`/`.jpeg`, `.webp`, up to 20 MB). A new upload clears the previous result.
- **Map size** in squares, pre-filled 25 × 25, with "detect map size from the image" as an option, off by default (it adds about $0.03 and fails on faint grids). A typed size wins.
- **Suggest walls:** the fast pass. Shows the mask over the map and a status line: model, time, estimated cost and the model's note on what it was unsure of.
- **Deeper examination:** enabled once a suggestion exists; a fresh trace with the stronger model that replaces the mask. A note says when it is worth paying for.
- **Accept mask:** always visible; downloads the mask on screen as `.dd2vtt` or `.uvtt`.
- **While a pass runs:** a progress indicator with elapsed time; the pass buttons are locked; the mask on screen can still be accepted.
- **On failure** (refusal, usage or rate limit, missing or invalid key, no network, timeout, unreadable response): a plain-language message, no crash, and any earlier mask stays.
- **Local first (decided 13.11):** the app, the data and every tool run on the laptop. The only thing that leaves the machine is the model call, made with the project owner's API key. Cloud deployment is optional and comes, if at all, after everything works locally.
- **Packaging:** everything runs on the laptop under Docker (Ubuntu 24.04, Python 3.12, CPU only), started with Docker Compose; the app is served on port 7860. App logic lives in plain functions apart from the UI, so tests run it with a fake client and never make a paid call.

## Timeline

Weeks 1–3 built the first approach; week 4 is the pivot; the app and the full evaluation follow, and the last two weeks are analysis and the presentation. Week-by-week tasks: [roadmap/](roadmap/README.md).

1. **20–26.10:** Requirements, labeling rules, .dd2vtt → mask rasterizer, repo and Docker, first 3 Dungeondraft maps, Roll20 format check. *Done.*
2. **27.10–2.11:** Synthetic generator, light labels, manifest, metrics, Canny baseline, evaluation harness, `dd04`–`dd08`. *Done.*
3. **3–9.11:** Colab training setup, stage-1 U-Net on synthetic data, EDA. *Done; last week of the first approach.*
4. **10–16.11:** **Pivot.** Spike, tracer v1 and v2, model comparisons, .dd2vtt writer, first Roll20 import from a traced map, app plan, spec and constitution, docs rewritten.
5. **17–23.11:** The app: two profiles, app logic, Gradio page, failure handling, map size worked out by the model. **Milestone: a file downloaded from the app imports into Roll20.**
   *Done on 13.11, ahead of plan; the Roll20 milestone is met.*
6. **24–30.11:** Results table from the existing runs; no new paid runs.
7. **1–7.12:** Polish from trying the app on new maps, demo setup. **Feature freeze 07.12.**
8. **8–14.12:** System card, failure gallery, exhibits, demo video. Workshop session 14.12 for feedback.
9. **15–23.12:** Slides, demo video, rehearsal. **Final presentation 23.12.**

## Risks & mitigations

| Risk | Likelihood | Mitigation |
| --- | --- | --- |
| API cost grows past what the project can spend | Medium | Cost shown per pass; a cost limit per map in the config; paid runs larger than a few maps approved one by one; tests use a fake client |
| The live demo depends on the network and the provider | Medium | A recorded demo video as backup; a finished mask stays downloadable when a later pass fails |
| Caves and complex structures are traced badly | High | The deep pass; the note next to its button; reported honestly |
| Results rest on one run per map; scores vary between runs | High | Every table says how many maps and runs are behind each cell; repeat runs on the reference maps before calling a change better or worse |
| The model gets the map size wrong, shifting every wall | Medium | The size stays editable and a typed size wins; correcting it costs nothing; accuracy is measured |
| The model refuses, or a usage or rate limit stops a pass | Low | Plain-language message; the earlier mask stays; a fallback model for declined requests is set in the config |
| A model is changed or retired by the provider before 23.12 | Low | Model names and prices live in one config file; the reference maps re-score any replacement |
| Roll20 reads the file differently than expected | Low | Proven on 13.11 with a traced tavern map; checked again from the app in week 5 |
| The comparison looks unfair to the trained model | Medium | Say plainly that stage 2 was never run; show the stage-1 numbers as they are |
| Time pressure in December | Medium | Feature freeze on 07.12; the last two weeks are analysis and writing only |

## Deliverables & open questions

**Deliverables for 23.12:**

- [ ] GitHub repo: tracer, writer, app, evaluation, and the first approach (generator, rasterizer, training)
- [ ] Results: the comparison table from the existing runs, costs, failure gallery, and a system card (models used, data, metrics, limitations, cost, privacy)
- [ ] The first approach's record: saved datasets (images, .dd2vtt, masks, manifest), the stage-1 run with its curves and learning progression
- [ ] Live demo on the laptop, with a recorded video as backup
- [ ] Presentation slides + a 2-minute demo video (map → app → file → Roll20 fog of war)

**Answered:**

- [x] Pretrained models may be used (asked in week 1).
- [x] Solo; the plan is scoped for one person.
- [x] Final submission (26.10): the presentation (up to 12 minutes), a demo and the code repo.
- [x] Doors vs. windows: not in the .dd2vtt, so one portal class only.
- [x] `.dungeondraft_map` files: out of scope; images and .dd2vtt only.
- [x] A large model in place of a trained one: allowed by the course staff (13.11).

**Open:**

- [ ] How many test-set maps to hand-trace.
