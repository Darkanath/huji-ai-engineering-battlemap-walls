# Week 6 · 24–30.11 · Ablations, grid detection, final test set

**Goal:** the planned ablation runs done, the scale found from the image when a grid is visible,
and the test set frozen.

## You

- [ ] Finalize the test set: 10–15 maps, split into **in-domain** (Dungeondraft-like) and **hard**
      (outdoor, photoreal). Record which is which in `docs/dungeondraft-maps.md` or a test-set log.
- [ ] Start one ablation run per night.

## Code

| File | What |
| --- | --- |
| `train/configs/ablation_real_only.toml` | U-Net trained on Dungeondraft only. |
| `train/configs/ablation_synthetic_only.toml` | Stage 1 model, no fine-tuning (reuses the week 3 run if its config matches). |
| `train/configs/ablation_no_scale_norm.toml` | Same as the main run but without rescaling to 32 px per square. |
| `train/configs/ablation_mobilenet.toml` *(stretch)* | MobileNetV3 encoder: accuracy vs CPU speed. |
| `data/grid.py` | Detect a visible square grid (line periodicity in the image) and return px per square, or `None`; the pipeline then falls back to the user's map width. |
| `tests/test_grid.py` | Finds the grid on the demo map (70 px); returns `None` on a map exported without a grid. |
| `eval/report.py` | Collect MLflow runs into the results table and the training-curve figures for the slides. |

About 6 training runs in total: stage 1, stage 2, real-only, no scale normalization, MobileNet,
plus Canny. Decide the list now and do not add to it.

## Run

```bash
docker compose run --rm app python -m train.train --config train/configs/ablation_real_only.toml
docker compose run --rm app python -m eval.report --split val
```

## Done when

- [ ] All planned ablation runs finished and scored on validation.
- [ ] Grid detection works on grid maps and falls back cleanly on gridless ones.
- [ ] Test set frozen: 10–15 maps, in-domain and hard, all traced and checked.
- [ ] Final model chosen by validation boundary F1. **No test-set runs yet.**

## Report

- Ablation table on validation (real-only vs synthetic-only vs synthetic -> real; with vs without scale normalization).

## Dependencies

None new.
