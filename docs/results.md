# Results

Scores of every trained model, filled in as runs finish. Validation results pick the model;
the test set runs once, in week 8 (training.md §6). How each run is trained: [training.md](training.md).
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
