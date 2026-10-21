# Week 6 · 24–30.11 · Ablations, grid detection, final test set

**Goal:** the planned ablation runs done, the scale found from the image when a grid is visible,
lights turned from mask blobs into .dd2vtt lights, and the test set frozen.

## You

- [ ] Finalize the test set: 10–15 maps, split into **in-domain** (Dungeondraft-like or Dungeon
      Alchemist-like) and **hard** (outdoor, photoreal). Record which is which in
      `data/raw/test/test_maps.csv` and `docs/map-log.md`.
- [ ] Run the ablations on Colab (`notebooks/colab_train.ipynb`), one config each; copy each
      `runs/<run>/` back to the laptop.

## Code

| File | What |
| --- | --- |
| `train/configs/ablation_real_only.toml` | U-Net trained on the real maps only (Dungeondraft + Dungeon Alchemist). |
| `train/configs/ablation_synthetic_only.toml` | Stage 1 model, no fine-tuning (reuses the week 3 run if its config matches). |
| `train/configs/ablation_no_scale_norm.toml` | Same as the main run but without rescaling to 32 px per square. |
| `train/configs/ablation_mobilenet.toml` *(stretch)* | MobileNetV3 encoder: accuracy vs CPU speed. |
| `data/grid.py` | Detect a visible square grid (line periodicity in the image) and return px per square, or `None`; the pipeline then falls back to the user's map width. |
| `tests/test_grid.py` | Finds the grid on the demo map (70 px); returns `None` on a map exported without a grid. |
| `eval/report.py` | Collect MLflow runs into the results table and the training-curve figures for the slides. |
| `postprocess/lights.py` *(lights)* | Light blobs (drop ones under a minimum area) -> centroid = position, equivalent radius -> nearest tier (thresholds halfway between the label radii) -> `range` and `intensity` from the tier table. Wired into `app/pipeline.py` and the writer. |
| `postprocess/configs/lights.toml` *(lights)* | The output tier table: bright and dim, `range`, `intensity` per tier (label radii and tier ranges stay in `LIGHT_TIERS`, `data/rasterize.py`). Must match `docs/labeling-rules.md`. |
| `eval/metrics.py` *(lights)* | Light F1 (one-to-one match within 0.5 squares) and tier accuracy on matched lights; added to `eval/evaluate.py`. |
| `tests/test_lights.py` *(lights)* | Round trip on a hand-made map: rasterize -> `lights.py` returns the same positions (within 0.1 square) and tiers; a light disc cut by a wall still gives one light; light F1 is 1 for a perfect prediction and 0 for none. |

About 6 training runs in total: stage 1, stage 2, real-only, no scale normalization, MobileNet,
plus Canny. Decide the list now and do not add to it.

## Run

```bash
# On Colab: notebooks/colab_train.ipynb with train/configs/ablation_real_only.toml (and the others)
docker compose run --rm app python -m eval.report --split val
```

## Done when

- [ ] All planned ablation runs finished and scored on validation.
- [ ] Grid detection works on grid maps and falls back cleanly on gridless ones.
- [ ] Test set frozen: 10–15 maps, in-domain and hard, all traced and checked.
- [ ] Final model chosen by validation boundary F1. **No test-set runs yet.**
- [ ] *(lights)* Light F1 and tier accuracy on validation for the chosen model; the predicted
      lights of one validation map import into Roll20.

## Report

- Ablation table on validation (real-only vs synthetic-only vs synthetic -> real; with vs without scale normalization), with light F1 and tier accuracy columns.

## Dependencies

None new.
