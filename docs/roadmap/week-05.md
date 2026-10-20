# Week 5 · 17–23.11 · End to end, visibility IoU · Milestone: first Roll20 import

**Goal:** one command turns a map image into a .dd2vtt that imports into Roll20 with usable fog
of war; visibility IoU measures what players actually see.

## You

- [ ] Run the pipeline on 2–3 Dungeondraft validation maps, upload the .dd2vtt files to Roll20,
      and time how long the manual fixes take. Note the times in `docs/results.md`.
- [ ] **Milestone:** first Roll20 import from a model prediction.

## Code

| File | What |
| --- | --- |
| `app/pipeline.py` | Image (`.png`, `.jpg`/`.jpeg`, `.webp`) + map width in squares -> rescale to 32 px per square -> `train.predict` -> `postprocess` -> .dd2vtt at 70 px per square. Also a CLI. |
| `eval/visibility.py` | Visibility IoU: ~100 random viewpoints inside each map, visibility polygon with predicted walls and with true walls, IoU averaged over viewpoints. Seeded. |
| `tests/test_pipeline.py` | A JPEG of the demo map goes in, a valid .dd2vtt comes out (uses a tiny untrained model, checks format only). |
| `tests/test_visibility.py` | Identical walls score 1; a wall with a gap scores lower than the full wall; a closed room seen from outside is empty. |
| `docs/results.md` | Start the results write-up: tables, Roll20 fix times, notes. |

Add visibility IoU to `eval/evaluate.py`, so every predictor gets all three metric levels.

## Run

```bash
docker compose run --rm app python -m app.pipeline data/processed/dungeondraft/dd01_a_image.jpg --squares 25 --out runs/e2e/
docker compose run --rm app python -m eval.evaluate --predictor unet --split val
docker compose run --rm app python -m eval.evaluate --predictor canny --split val
```

## Done when

- [ ] A predicted .dd2vtt imports into Roll20 with working walls, doors and fog of war.
- [ ] Validation results table has Canny and U-Net rows with pixel, boundary and visibility metrics.
- [ ] All tests pass.

## Report

- Validation results table (all three metric levels), first Roll20 fix times.

## Dependencies

- `shapely` (visibility polygons; in CLAUDE.md).
