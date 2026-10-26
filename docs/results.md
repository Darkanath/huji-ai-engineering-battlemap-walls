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
