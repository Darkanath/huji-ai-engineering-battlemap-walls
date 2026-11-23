# Results

Scores of every predictor, filled in as runs finish: the Canny baseline, the stage-1 U-Net
(first approach; how it was trained: [history/training.md](history/training.md)) and the Claude tracer. The test
set runs once, in week 8.
Metrics: [eval/metrics.py](../eval/metrics.py), at 32 px per square; boundary F1 tolerance 0.1
square (3 px).

## Data (EDA, 26.10)

From `notebooks/eda.ipynb` (figures in `runs/eda/`, not committed: `examples.png` shows map
crops). Pixel shares weight maps by area.

| Dataset | Maps (train / val / test) | Wall | Portal | Light | Lights per map (S / M / L) |
| --- | --- | --- | --- | --- | --- |
| Synthetic | 450 / 50 / 0 | 8.7% | 1.4% | 0.37% | 2.9 / 1.7 / 0.8 |
| Dungeondraft | 8 / 4 / 4 | 4.7% | 0.7% | 0.07% | 1.0 / 0.5 / 0 |
| Dungeon Alchemist | 2 / 0 / 0 | 2.7% | 0.8% | 0.78% | 20 / 3 / 0 |

- **Wall share** is wall length per map, since labels have a fixed width: synthetic maps have
  smaller rooms and walls up to the edge.
- **Brightness:** real Dungeondraft maps sit at the bright end of the synthetic range (mean value
  100-170 vs 20-140); the two Dungeon Alchemist maps are the most saturated.
- **Portals** are mostly 1 square wide; Dungeondraft has narrower windows (0.75-1) and a
  3-square double door (`dd04`); Dungeon Alchemist double doors are pairs of 1-square portals,
  so they show as 2 squares (4 where two pairs touch).
- **Lights:** Dungeon Alchemist puts a candle on nearly every table (about 20 small lights per
  map); no real map has a large light yet (first one planned in `dd07`).

## Validation

Real val = Dungeondraft + Dungeon Alchemist validation layouts, the set that selects
checkpoints. As of 26.10 it is a single layout, `dd03` (4 variants, no lights, no furniture),
so the numbers are noisy and the Canny baseline was tuned on these same maps (optimistic).

| Model | Set | Maps | Wall IoU | Wall boundary F1 | Portal IoU | Light IoU |
| --- | --- | --- | --- | --- | --- | --- |
| R0 Canny baseline | real val | 4 | 0.384 | **0.845** | 0 | - |
| R1 U-Net, synthetic only (epoch 16) | real val | 4 | **0.520** | 0.843 | **0.355** | 0 (specks only, below) |
| R0 Canny baseline | synthetic val | 50 | 0.180 | 0.511 | 0 | 0 |
| R1 U-Net, synthetic only (epoch 16) | synthetic val | 50 | **0.903** | **0.996** | **0.834** | **0.944** |

Per-map scores: `runs/canny_val/metrics.csv`, `runs/r1_val/metrics.csv`
(`python -m eval.evaluate --predictor unet --checkpoint runs/r1_stage1_synthetic/best.pt --split val --run r1_val`).

## R1 · stage 1, synthetic only (26.10)

- **Run:** Colab, Tesla T4, `train/configs/stage1_synthetic.toml`, data pack `data-e92adbca18`
  (450 synthetic train maps). Early stop after epoch 24 of 30 (8 epochs without a better real-val
  boundary F1); best epoch 16. About 2 min per epoch, 45 min in all.
- **Curves** (`runs/r1_stage1_synthetic/metrics.csv`, MLflow): training loss falls steadily
  (0.97 -> 0.24). Real-val boundary F1 jumps when the encoder is unfrozen (epoch 5: 0.33,
  epoch 7: 0.81), then plateaus around 0.75-0.84 and bounces from epoch to epoch while the
  training loss keeps falling: the model keeps fitting the synthetic style without getting better
  on real maps. That is the synthetic-to-real gap the EDA shows (real maps brighter, with less wall per map),
  and the reason for stage 2.
- **Learning progression** (`runs/sheets/r1_progression_dd03_a.jpg`, epochs 1 / 6 / 16 on
  `dd03_a`): epoch 1 finds the walls but calls them all portals (the class weights push hard
  toward the rare classes early on); epoch 6 separates walls from portals but the walls are
  dashed; epoch 16 has mostly solid walls with doors in place, missing short stretches of the
  narrow 1-square corridors.
- **Lights on a map without lights:** 0-166 predicted light pixels per `dd03` map (of 640,000),
  isolated specks. The light post-processing's minimum blob size (week 6) removes them; light IoU
  on `dd03` stays 0 until then because any false pixel on a light-free map scores 0.
- **Versus Canny:** better wall IoU on real val (0.52 vs 0.38), equal boundary F1 (0.84), and it
  finds portals, which Canny cannot; on synthetic val far ahead on every metric.

## LLM spike · Claude reads the map directly (13.11)

After the course staff allowed a large model in place of a trained one (13.11), a spike tested
whether Claude can place walls, portals and lights straight from the image. Claude (Fable 5.2,
inside a Claude Code session, not yet an API pipeline) looked at the map image only: the full
image, four zoomed crops with a labeled square grid, and a few closer crops where needed. It
answered with polylines, arcs, portals and lights in grid squares. The answer was rasterized
with `data/rasterize.py` and scored with `eval/metrics.py` at 32 px per square, like every model.
Files: `runs/llm_spike/` (answers, previews, scores; not committed).

| Map | Predictor | Wall IoU | Wall boundary F1 | Portal IoU | Light IoU |
| --- | --- | --- | --- | --- | --- |
| `dd07_a` castle, round towers | Claude | **0.885** | **0.995** | **0.742** | **0.412** |
| | R1 U-Net, synthetic only | 0.323 | 0.664 | 0.303 | 0.239 |
| | R0 Canny baseline | 0.010 | 0.058 | 0 | 0 |
| `dd06_a` mine, cave walls | Claude | **0.576** | **0.957** | **0.681** | **0.325** |
| | R1 U-Net, synthetic only | 0.047 | 0.118 | 0 | 0.168 |
| | R0 Canny baseline | 0.028 | 0.133 | 0 | 0 |

- **Third map, no labels:** `data/test/map-26x28.jpeg` (a published tavern map, test only).
  The resulting .dd2vtt imported into Roll20 with working fog of war; one mistake, an extra door
  inside the bathroom.
- **Reading the numbers:** boundary F1 is the fair wall metric here. Wall IoU on `dd06` is lower
  because a hand-traced cave line sits a fraction of a wall width off the label, which costs
  IoU on a thin class but not gameplay.
- **Not a fair fight for the U-Net:** R1 never trained on real maps (stage 2 was not run), and
  Canny was tuned on `dd03` only. Two maps is a small sample.
- **Small leaks:** before the spike, the session had seen the manifest's light counts per tier
  for these maps and commit messages mentioning their lights. Wall and portal geometry was not
  seen. Light scores may be slightly optimistic.
- **Cost of the method:** about 9-10 image views per map (overview, four quadrants, close-ups).
  One look at the full image is not precise enough to place doors.

## Claude tracer v1 · model comparison (13.11)

The spike turned into a pipeline (`llm/`): Claude gets the map with a labeled grid, asks for
zoomed crops, submits walls, portals and lights, and sees its answer drawn over the map.
One run per cell, effort as shown, scored like every model. Cost is estimated from the API's
token counts and the list prices in `llm/configs/claude.toml`. Runs: `runs/claude_*/`
(`python -m llm.run --maps dd07_a dd06_a --run NAME --model MODEL --effort EFFORT`).

| Map | Model | Wall IoU | Wall boundary F1 | Portal IoU | Light IoU | Views | Cost | Time |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| `dd07_a` castle | Opus 5.5, medium | **0.713** | **0.983** | 0.251 | 0.530 | 3 | $0.23 | 57 s |
| | Opus 5.5, high | 0.670 | 0.962 | **0.384** | **0.659** | 8 | $0.26 | 62 s |
| | Sonnet 5.5, medium | 0.530 | 0.918 | 0 | 0.497 | 0 | $0.06 | 21 s |
| | Haiku 5.5, medium | 0.296 | 0.500 | 0 | 0.474 | 1 | $0.01 | 36 s |
| `dd06_a` mine | Opus 5.5, medium | **0.451** | **0.882** | **0.593** | **0.317** | 4 | $0.46 | 126 s |
| | Opus 5.5, high | 0.427 | 0.860 | 0.569 | 0.301 | 4 | $0.41 | 133 s |
| | Sonnet 5.5, medium | 0.109 | 0.330 | 0 | 0.147 | 0 | $0.03 | 9 s |
| | Haiku 5.5, medium | 0.175 | 0.467 | 0.261 | 0.172 | 0 | $0.01 | 31 s |

- **Only Opus 5.5 is usable so far.** It beats the U-Net and Canny on both maps (table above),
  at $0.23-0.46 per map. Sonnet and Haiku answered almost without zooming in and missed
  the cave walls.
- **High effort did not help** over medium on these two maps; the differences are within what
  one run each can show.
- **Below the spike.** The in-session Fable 5.2 spike scored 0.995 and 0.957 boundary F1 with
  9-10 views per map; Opus used 3-8 and missed the tower doors and wall windows on `dd07`.
  The models look less than the task needs, so v2 should not leave looking to their choice.
- Whole comparison: about $1.46.

## Claude tracer v2 · map quarters sent up front (13.11)

One change from v1: the first message holds the whole map plus its four quarters at higher
zoom (`views.quadrants` in `llm/configs/claude.toml`), so close reading no longer depends on the
model asking for it. Medium effort, one run per cell. Runs: `runs/claude_v2_*/`.

| Map | Model | Wall IoU | Wall boundary F1 | Portal IoU | Light IoU | Extra views | Cost | Time |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| `dd07_a` castle | Fable 5.2 | **0.839** | **0.996** | **0.903** | 0.643 | 3 | $0.40 | 35 s |
| | Opus 5.5 | 0.836 | 0.989 | 0.701 | **0.664** | 2 | $0.28 | 62 s |
| | Sonnet 5.5 | 0.688 | 0.960 | 0 | 0.590 | 0 | $0.08 | 20 s |
| `dd06_a` mine | Fable 5.2 | **0.503** | **0.924** | **0.656** | 0.311 | 0 | $0.46 | 50 s |
| | Opus 5.5 | 0.436 | 0.881 | 0.575 | **0.316** | 0 | $0.25 | 61 s |
| | Sonnet 5.5 | 0.280 | 0.664 | 0.608 | 0.080 | 0 | $0.07 | 19 s |

- **The quarters help every model.** Opus portal IoU on the castle went from 0.25 to 0.70 and
  its wall IoU from 0.71 to 0.84; Sonnet's cave boundary F1 doubled (0.33 to 0.66).
- **Fable 5.2 is the most accurate** and matches the in-session spike on the castle; Opus 5.5
  is close on walls for about 60% of the cost. Sonnet 5.5 is still well behind on caves and
  finds no portals on the castle.
- **Caves remain the weak spot** (0.88-0.92 boundary F1 against 0.99 on the castle): no model
  asked for a closer view of the mine.
- Whole comparison: about $1.54. Both comparisons together: about $3.

## Reference evaluation · both app profiles with the map-size step (13.11)

The first scored run of the app's two profiles as configured (`[profiles.quick]` Sonnet 5.5,
`[profiles.deep]` Opus 5.5, both medium effort, v2 harness), on the four committed reference
maps in `data/reference/`, with the new map-size step (`--detect-size`) before each trace. One
run per cell. Traced and scored on the true map size (25 x 25), so scores compare with v2;
the detected size is recorded separately. Portal recall: share of labeled portals with a
predicted midpoint within 0.5 square, matched one to one (`eval.metrics.portal_recall`).

Commands: `python -m llm.run --reference --profile quick --detect-size` and the same with
`--profile deep`. Runs: `runs/20261113-134942_quick/`, `runs/20261113-135137_deep/`.

| Map | Profile | Wall IoU | Wall boundary F1 | Portal IoU | Portal recall | Light IoU | Size found | Extra views | Cost | Time |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| `dd04_a` tavern | quick | 0.671 | 0.841 | 0 | 0 / 23 | 0.334 | 25 x 25, right | 0 | $0.07 | 14 s |
| | deep | 0.622 | 0.963 | 0.640 | 1.00 | 0.342 | 25 x 25, right | 6 | $0.31 | 64 s |
| `dd06_a` mine | quick | 0.208 | 0.545 | 0.189 | 0.25 | 0.079 | 18 x 18, wrong | 0 | $0.08 | 23 s |
| | deep | 0.464 | 0.893 | 0.660 | 0.75 | 0.440 | 25 x 25, right | 0 | $0.41 | 104 s |
| `dd07_a` castle | quick | 0.712 | 0.909 | 0 | 0 / 17 | 0.534 | 20 x 20, wrong | 0 | $0.10 | 29 s |
| | deep | 0.758 | 0.992 | 0.785 | 0.94 | 0.659 | 25 x 25, right | 1 | $0.30 | 62 s |
| `dd04_d` tavern, no grid | quick | 0.747 | 0.916 | 0.169 | 0.09 | 0.227 | none (correct) | 0 | $0.09 | 21 s |
| | deep | 0.916 | 0.999 | 0.805 | 1.00 | 0.232 | none (correct) | 4 | $0.28 | 48 s |

Means per map, including the map-size step: quick $0.085 and 22 s; deep $0.32 and 70 s
(config before this run: $0.07 / 20 s and $0.27 / 60 s).

Against the spec's thresholds (quickstart.md section 4):

- **Deep pass: all met.** Castle wall boundary F1 0.992 (floor 0.95) and portal recall 0.94
  (floor 0.5); mine 0.893 (floor 0.85).
- **Quick pass, castle: 0.909, under the 0.95 floor.** The v2 run scored 0.960 on the same
  map. Re-scoring the v2 answer with this run's scoring path gives 0.960 again, so scoring did
  not change; the tracing code was not changed either. One run per cell cannot tell variance
  from regression; the quickstart rule is to repeat a run under a floor before calling it one.
- **Quick pass finds almost no doors on buildings** (0 of 23 on the tavern, 0 of 17 on the
  castle), as in v2, and never asks for a closer view. The deep pass finds nearly all of them.
- **Map size: deep 3 of 3 right, quick 1 of 3** (the mine read as 18 x 18 and the castle as
  20 x 20). Both reported "no grid" on the grid-less tavern. The quick pass is under SC-009's
  80% target. In the app, a wrong detected size means the mask is traced on the wrong grid,
  then shown on that size until the user corrects it.
- **Time:** the slowest deep pass (mine, 104 s) is inside the 180 s deadline; quick passes
  (14-29 s) are inside 60 s.
- Whole evaluation: $1.63 (estimated $1.40).

### Castle repeat, and the map-size step moved to Opus (13.11)

The quick pass scored 0.909 on the castle above, under its 0.95 floor. Following the
quickstart rule, the map was traced again before calling it a regression; this run also uses
the decision taken after the table above: **the map-size step runs on Opus in both passes**
(`[size_step] profile = "deep"` in the config), because Sonnet found the size on 1 of 3 grid
maps and Opus on 3 of 3.

Command: `python -m llm.run --maps dd07_a --profile quick --detect-size --run
20261113-quick-castle-repeat`. One run.

| Map | Profile | Wall IoU | Wall boundary F1 | Portal IoU | Portal recall | Light IoU | Size found (Opus) | Size step cost | Total cost | Time |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| `dd07_a` castle | quick | 0.685 | **0.966** | 0 | 0 / 17 | 0.475 | 25 x 25, right | $0.026 | $0.08 | 17 s |

- **Not a regression:** 0.966 is above the floor and next to v2's 0.960. Three quick runs on the
  castle now span 0.909 to 0.966; one run per cell is not enough to rank close results.
- **The quick pass still finds no castle doors** in any of its three runs.
- **Map size with Opus: 4 of 4 runs right** on maps with a grid; SC-009's 80% target stands.
- **Shown estimates updated** (`llm/configs/claude.toml`): quick about 25 s and $0.10 (the
  $0.085 mean above plus the difference between the Opus and the Sonnet size step, rounded
  up), deep about 70 s and $0.32. Before: 20 s / $0.07 and 60 s / $0.27.
- Cost of this run: $0.08. Reference evaluation in all: $1.71.

## Roll20 import from the app, and a map-size miss (T063, 13.11)

The owner uploaded a `.dd2vtt` downloaded from the app to Roll20 (Page Menu -> Upload
Background). The import worked: walls, doors and lights came in and fog of war followed the
walls. The week-5 milestone is met.

The map used was a third-party map (`runs/test-maps/lakeside-tavern-2.png`, 2240 x 1280 px,
not committed). Its grid is 64 px per square, so the map is **35 x 20** squares; measured by
folding the grass bands' brightness profile, where both axes peak at 64 px. The grid is faint
and visible only on the grass around the building; the floor art covers it.

- **In the app, the map-size step reported 56 x 32** (40 px squares), so Roll20 drew its grid
  at the wrong scale. 56 x 32 has the same proportions as 35 x 20, so the non-square-cells
  warning could not catch it. Correcting the size in the app and accepting again fixes the
  file without a new pass.
- **A single re-run of the size step alone** (Opus, $0.03) answered 35 x 20, but its own
  note said the lines were too faint to count and it estimated from the spacing. Detection on
  maps like this is unreliable; one run each cannot say how often it fails.
- **Why:** the overview is downscaled to 1300 px (64 px squares become about 37 px, and the
  faint lines nearly vanish); the top and left edge strips are 12% of the map and mostly
  show the building, with only about 55 px of grass above it.
- The size step was measured only on the owner's Dungeondraft maps (clear grid lines) before
  this; this is the first map with a faint, partly covered grid.

### Map-size step with pixel rulers (13.11)

One change to the size step only: every image it sends gets pixel rulers in its margins,
labeled in original-image pixels; the model reports the square size in pixels as well as the
size in squares, and a count more than 5% off image size / square size is replaced by the
ruler reading. Opus, two runs per map. Command: `python -m llm.run --reference --image
runs/test-maps/lakeside-tavern-2.png --squares 35 20 --size-only` (runs
`runs/20261113-size-ruler-1/`, `-2/`). Cost $0.28.

| Map | Before (old views) | With rulers |
| --- | --- | --- |
| `dd04_a` tavern, `dd06_a` mine | right in every run | 4 of 4 right |
| `dd07_a` castle | 4 of 4 right | **0 of 2** (18 x 18, 27 x 27) |
| `dd04_d` no grid | "no grid" 2 of 2 | 1 of 2 ("no grid"; once 35 x 35 from floor tiles) |
| lakeside tavern, faint grid | 1 of 2 (the app's run said 56 x 32) | **2 of 2** |

- The model read the grid lines correctly but mishandled the scale: on the castle it found
  lines 70 px apart (right) and then "converted" them with a scale it misread from the ruler.
  Its counts and square sizes agreed with each other, so the 5% check never fired.
- **Not adopted:** better on the faint grid, worse on the castle and the no-grid map.
- **Decision (owner):** no more spending on detection for now. "Detect map size from the
  image" is **off by default** (`[app] detect_size_default = false`); the user ticks it when
  wanted. The size note now shows the implied px per square (e.g. "56 x 32 squares, 40 px
  per square"), so a wrong count is easy to spot and correct for free.

## Chunked tracing · reference maps (23.11)

The chunked pass (`specs/002-chunked-map-tracing/`): the map is split into parts, each traced
by its own agent (at most 4 at a time), the answers are merged by fixed rules, and an
orchestrator model (Sonnet) rewrites the strips 1 square either side of each border. Sonnet
agents get 13-square parts (4 per 25 x 25 map), Haiku agents 7-square parts (16 per map).
Merge as fixed on 23.11 (commit `b6cb8a1`: borders at quarter squares, one-to-one joins).
Traced and scored on the true map size (25 x 25, no size step), at 32 px per square, against
the four reference maps. **One run per map.** The rule-merged answer and the reviewed one are
scored from the same run.

Commands: `python -m llm.run --reference --chunked --agents sonnet --run 20261123_chunked_sonnet`
and the same with `--agents haiku --run 20261123_chunked_haiku`. Runs:
`runs/20261123_chunked_sonnet/`, `runs/20261123_chunked_haiku/`. Cost: $0.83 (Sonnet) +
$0.59 (Haiku) = **$1.42** (estimated before the run: $1.7). Opus agents were not run.

Figures: `python -m eval.figures` writes `docs/figures/` from the runs' `summary.csv` files.

### Means over the four maps

| Method | Wall boundary F1, mean | worst map | Portal recall, mean | Light IoU, mean | Cost per map | Time per map |
| --- | --- | --- | --- | --- | --- | --- |
| Single session, Sonnet (13.11) | 0.803 | 0.545 | 0.08 | 0.293 | $0.085 | 22 s |
| Single session, Opus (13.11) | **0.962** | **0.893** | **0.92** | 0.418 | $0.324 | 70 s |
| Chunked, Sonnet agents (4 parts) | 0.832 | 0.728 | 0.26 | 0.323 | $0.207 | 30 s |
| Chunked, Haiku agents (16 parts) | 0.898 | 0.816 | 0.70 | **0.457** | $0.147 | 103 s |

![Wall boundary F1 per reference map](figures/boundary_f1_wall.png)

![Doors and windows found per reference map](figures/portal_recall.png)

### Per map, chunked runs

"Merged" is the rule merge before the border review; the other scores are the final answer.
"Hanging ends" counts wall ends left on a border with no wall within 0.1 square (spec SC-003).

| Map | Agents | Wall IoU | Wall boundary F1 | Merged F1 | Portal recall | Light IoU | Hanging ends (merged → final) | Cost | Time |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| `dd04_a` tavern | Sonnet | 0.522 | 0.846 | 0.839 | 0 / 23 | 0.123 | 1 → 0 | $0.17 | 21 s |
| | Haiku | 0.714 | 0.907 | 0.906 | 0.83 | 0.451 | 2 → 2 | $0.14 | 96 s |
| `dd04_d` tavern, no grid | Sonnet | 0.391 | 0.839 | 0.854 | 0.22 | 0.218 | 0 → 0 | $0.18 | 20 s |
| | Haiku | 0.792 | 0.952 | 0.952 | 0.87 | 0.359 | 0 → 0 | $0.13 | 91 s |
| `dd06_a` mine | Sonnet | 0.330 | 0.728 | 0.750 | 0.75 | 0.478 | 4 → 0 | $0.24 | 42 s |
| | Haiku | 0.513 | 0.918 | 0.923 | 0.75 | 0.443 | 7 → 4 | $0.14 | 95 s |
| `dd07_a` castle | Sonnet | 0.571 | 0.915 | 0.930 | 0.06 | 0.472 | 0 → 0 | $0.24 | 36 s |
| | Haiku | 0.560 | 0.816 | 0.761 | 0.35 (merged 0.41) | 0.576 | 12 → 0 | $0.18 | 131 s |

No part failed or was skipped in either run, and no door or light was counted twice.

![Estimated cost per map](figures/cost_per_map.png)

![Time per map](figures/time_per_map.png)

### Does the border review help?

![Rule merge against the reviewed answer](figures/review_effect.png)

- **Sonnet agents (2 borders):** the review lowered wall boundary F1 on 3 of 4 maps (by
  0.015-0.023) and raised it on 1 (+0.007). It removed every hanging wall end (5 → 0).
- **Haiku agents (6 borders, the strips cover about half the map):** no change on three maps;
  on the castle it raised wall F1 by 0.055 (and wall IoU by 0.058) and removed all 12 hanging
  ends, but lost one door (portal recall 0.41 → 0.35).
- It costs $0.03-0.06 per map with 4 parts and $0.09-0.12 with 16.

### Against the success criteria (spec 002)

| Criterion | Result |
| --- | --- |
| SC-001: chunked wall F1 >= single session with the same model on every map; mine above 0.545 with the fast model | **Partly.** Sonnet: mine 0.545 → **0.728**, tavern and castle equal or better, but the no-grid tavern lower (0.916 → 0.839). Haiku has no comparable single-session run (v1 harness on 13.11: castle 0.500, mine 0.467; chunked: 0.816, 0.918) |
| SC-002: portal recall >= single session; above 0 on the tavern and the castle with the fast model | **Partly.** Sonnet: equal or better everywhere, castle 0 → 0.06, but the tavern still 0 of 23. Haiku agents find most doors on both taverns (0.83, 0.87) |
| SC-003: no border gap over 0.1 square, nothing counted twice | **Met for Sonnet** (0 hanging ends, 0 duplicates). **Not met for Haiku**: 2 hanging ends on the tavern and 4 on the mine after the review; 0 duplicates |
| SC-004 (amended 23.11): Sonnet at most twice the single session; Haiku at most 3 minutes | **Met.** Sonnet 20-42 s against 28-58 s allowed; Haiku 91-131 s |
| SC-005: estimate shown before within 50% of the actual cost | **Met.** Sonnet estimate $0.29 against $0.17-0.24 (−17% to −40%); Haiku $0.13 against $0.13-0.18 (+2% to +37%) |
| SC-009: the review never lowers wall F1 or portal recall | **Not met.** Lower wall F1 on 3 of 4 Sonnet maps (by up to 0.023) and lower portal recall on the Haiku castle |

### What this shows

- **Chunking pays most with a small model.** Haiku agents on 16 parts scored a mean wall F1
  of 0.898 and portal recall of 0.70, well above the single-session Sonnet pass (0.803, 0.08)
  and Sonnet agents on 4 parts (0.832, 0.26), at $0.15 a map. Small parts made Haiku look
  closer: it asked for a closer view in 36 of its 64 parts, where Sonnet agents asked in 1 of
  16 and the single-session passes in almost none (13.11).
- **Opus in one session is still the most accurate** (0.962, 0.92) and costs about twice as
  much as Haiku chunked, but runs faster (70 s against 103 s).
- **Sonnet agents with 4 parts** fixed the cave (0.545 → 0.728) but still miss the doors in
  buildings: like the single session, they almost never asked for a closer view (1 of 16
  parts).
- **The border review is a trade-off, not a free gain.** It cleans up joins (hanging ends to
  zero in 6 of 8 runs) but mostly shaves a little wall accuracy, so SC-009 is not met.

Known weaknesses: one run per map, so differences under about 0.03 are within run-to-run
noise; four maps, all 25 x 25 at 70 px per square (research.md R1), two of them (the taverns) the
same layout in two styles; the single-session rows are from 13.11, a different day; Opus agents not run.
Measured time and cost now replace the estimates in `llm/configs/claude.toml` for Sonnet and
Haiku (T044).
