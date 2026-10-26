# Week 2 · 27.10–2.11 · Manifest, synthetic generator, metrics, Canny baseline

**Goal:** every dataset can be built to disk with one command and listed in a manifest; synthetic
maps can be generated; predictions can be scored; the classical baseline has a first score.

## You

- [ ] 5 more Dungeondraft layouts × 4 variants: `dd04`–`dd08`, as specified in
      [map-specs.md](../map-specs.md).
- [x] Upload `dd04_a.dd2vtt` (the first export with lights) to Roll20 and note how each tier's
      light imports (bright and dim radius from `range` and `intensity`) in
      `docs/labeling-rules.md`. Also check that `range` in the .dd2vtt is in grid squares. Do this
      before finishing the other layouts: if the unit is wrong, every light's range changes.
      *Done 21.10: imports fine, `range` is in grid squares.*
- [ ] *(optional)* Pick a small set of CC0 textures (floors, walls), furniture sprites and light
      source sprites (torch, candle, lantern, brazier, campfire, bonfire; lit and unlit) and put
      them in `data/assets/` with a `SOURCES.md` listing where each came from. Only CC0 or your
      own work. The generator v1 draws everything procedurally, so it doesn't need them; assets
      would only make synthetic maps look more like real ones.
- [ ] If the Roll20 upload from week 1 is not done yet, do it now.

## Code

| File | What |
| --- | --- |
| `data/manifest.py` *(done)* | Scan the top level of `data/raw/<dataset>/` (not `original/` subfolders), read layout and variant from `<layout>_<variant>`, assign splits by layout with a fixed seed, per dataset (Dungeondraft and Dungeon Alchemist each 70/15/15 with at least one layout in val and in test, synthetic 90/10, `test/` always test), rasterize every map into `data/processed/<dataset>/` at 70 px and write the 32 px training copies into `data/processed/<dataset>/32px/` (training.md §2), write `data/processed/manifest.csv` (dataset, map, layout, variant, split, seed, pixel shares including light, light count per tier). Re-running it keeps existing splits. |
| `tests/test_manifest.py` *(done)* | Variants of a layout share a split; files in `original/` are skipped; same seed gives the same splits; CSV columns and shares are right. |
| `data/generator.py` + `data/synth/` *(done)* | Synthetic map generator (PLAN.md steps 1–7): rooms and corridors, doorless gaps of 1–3 squares, walls of varying width and color, doors and windows, light sprites of all three tiers with their `lights` entries (wall lights on the room side), unlit fixtures as distractors, furniture distractors, optional grid, tint, blur and JPEG noise. Writes `data/raw/synthetic/syn0001.dd2vtt` (embedded PNG image), one seed per map. Default 25×25 squares at 70 px. |
| `data/configs/generator.toml` *(done)* | Generator settings: counts, wall width range, gap, furniture and light probabilities, lights per map and tier mix. |
| `tests/test_generator.py` *(done)* | Same seed gives the same file; output loads with `load_uvtt`; rasterized mask has walls, portals, lights and at least one gap; every light's `range` is a tier value; shares in a sane range. |
| `eval/metrics.py` *(done)* | Pixel IoU and F1 per class (light included); wall boundary F1 with a 0.1-square tolerance. Light F1 and tier accuracy come in week 6. |
| `tests/test_metrics.py` *(done)* | Perfect prediction scores 1; empty prediction scores 0; a 2 px shift still scores high on boundary F1. |
| `eval/baseline_canny.py` *(done)* | Canny edges + contours -> wall mask, with thresholds read from a config. |
| `eval/configs/baseline_canny.toml` *(done)* | The thresholds, tuned once on the validation split, then frozen. |
| `eval/evaluate.py` *(done)* | Run a predictor over one split from the manifest and write per-map and mean metrics to `runs/<run>/metrics.csv`. |
| `tests/test_baseline.py`, `tests/test_evaluate.py` *(done)* | Runs on the demo map and returns a mask of the right shape and classes. |

## Run

```bash
docker compose run --rm app python -m data.generator --count 20      # small batch to check
docker compose run --rm app python -m data.manifest
docker compose run --rm app python -m eval.evaluate --predictor canny --split val
docker compose run --rm app pytest
```

## Done when

- [x] 20 synthetic maps generated; their previews look right by the labeling rules, lights included
      (contact sheet checked 21.10; walls are axis-aligned only in v1).
- [x] `manifest.csv` lists the demo, all Dungeondraft, Dungeon Alchemist and synthetic maps with splits.
- [x] Canny baseline tuned on validation, config frozen, validation scores saved
      (`runs/canny_val/metrics.csv`; tuned on `dd03` only, retuned once in week 4).
- [x] All tests pass (74 passed, 26.10).

## Report

- Data summary table (maps, pixel shares and light counts per tier, per split), from `manifest.csv`.
- First row of the results table: the Canny baseline on validation. 21.10, real val (`dd03`, 4
  maps): wall IoU 0.384, wall boundary F1 0.845, portal and light IoU 0. Synthetic val: wall
  IoU 0.177, boundary F1 0.531.

## Dependencies

- `opencv-python-headless` (Canny, contours, distance transform) and `scikit-image` (both in CLAUDE.md).
