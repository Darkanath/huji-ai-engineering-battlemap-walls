# Week 2 · 27.10–2.11 · Manifest, synthetic generator, metrics, Canny baseline

**Goal:** every dataset can be built to disk with one command and listed in a manifest; synthetic
maps can be generated; predictions can be scored; the classical baseline has a first score.

## You

- [ ] 5 more Dungeondraft layouts × 4 variants (`a`–`d`, one without grid): `dd04`–`dd08`.
- [ ] Pick a small set of CC0 textures (floors, walls) and furniture sprites for the generator and
      put them in `data/assets/` with a `SOURCES.md` listing where each came from. Only CC0 or
      your own work.
- [ ] If the Roll20 upload from week 1 is not done yet, do it now.

## Code

| File | What |
| --- | --- |
| `data/manifest.py` | Scan `data/raw/<dataset>/`, read layout and variant from `<layout>_<variant>`, assign splits by layout with a fixed seed (Dungeondraft 70/15/15, synthetic 90/10, `test/` always test), rasterize every map into `data/processed/<dataset>/` at 70 px and write the 32 px training copies into `data/processed/<dataset>/32px/` (training.md §2), write `data/processed/manifest.csv` (dataset, map, layout, variant, split, seed, pixel shares). Re-running it keeps existing splits. |
| `tests/test_manifest.py` | Variants of a layout share a split; same seed gives the same splits; CSV columns and shares are right. |
| `data/generator.py` | Synthetic map generator (PLAN.md steps 1–6): rooms and corridors, doorless gaps of 1–3 squares, walls of varying width and color, doors and windows, furniture distractors, optional grid, tint, blur and JPEG noise. Writes `data/raw/synthetic/syn0001.dd2vtt` (embedded PNG image), one seed per map. Default 25×25 squares at 70 px. |
| `data/configs/generator.toml` | Generator settings: counts, wall width range, gap and furniture probabilities. |
| `tests/test_generator.py` | Same seed gives the same file; output loads with `load_uvtt`; rasterized mask has walls, portals and at least one gap; shares in a sane range. |
| `eval/metrics.py` | Pixel IoU and F1 per class; wall boundary F1 with a 0.1-square tolerance. |
| `tests/test_metrics.py` | Perfect prediction scores 1; empty prediction scores 0; a 2 px shift still scores high on boundary F1. |
| `eval/baseline_canny.py` | Canny edges + contours -> wall mask, with thresholds read from a config. |
| `eval/configs/baseline_canny.toml` | The thresholds, tuned once on the validation split, then frozen. |
| `eval/evaluate.py` | Run a predictor over one split from the manifest and write per-map and mean metrics to `runs/<run>/metrics.csv`. |
| `tests/test_baseline.py` | Runs on the demo map and returns a mask of the right shape and classes. |

## Run

```bash
docker compose run --rm app python -m data.generator --count 20      # small batch to check
docker compose run --rm app python -m data.manifest
docker compose run --rm app python -m eval.evaluate --predictor canny --split val
docker compose run --rm app pytest
```

## Done when

- [ ] 20 synthetic maps generated; their previews look right by the labeling rules.
- [ ] `manifest.csv` lists the demo, all Dungeondraft and all synthetic maps with splits.
- [ ] Canny baseline tuned on validation, config frozen, validation scores saved.
- [ ] All tests pass.

## Report

- Data summary table (maps and pixel shares per split), from `manifest.csv`.
- First row of the results table: the Canny baseline on validation.

## Dependencies

- `opencv-python-headless` (Canny, contours, distance transform) and `scikit-image` (both in CLAUDE.md).
