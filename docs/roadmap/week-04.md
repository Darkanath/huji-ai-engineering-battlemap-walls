# Week 4 · 10–16.11 · Fine-tune on Dungeondraft; mask -> .dd2vtt

**Goal:** the stage 2 model fine-tuned on Dungeondraft maps, and the post-processing that turns a
predicted mask into a .dd2vtt. This is about half the engineering work, so it starts now.

## You

- [ ] Finish the Dungeondraft set: `dd14`–`dd18` × 4 variants, as specified in
      [map-specs.md](../map-specs.md) (18 layouts in total).
- [ ] Keep tracing test-set maps.

## Code

| File | What |
| --- | --- |
| `train/configs/stage2_dungeondraft.toml` | Stage 2: start from the stage 1 checkpoint, Dungeondraft train split, lower learning rate. |
| `train/predict.py` | Sliding-window inference: 256 windows with overlap, probabilities averaged at the seams; returns a class mask at the input's scale. |
| `postprocess/clean.py` | Morphological close with a kernel well under 0.25 square (doorless gaps stay open); drop blobs under a minimum area. |
| `postprocess/vectorize.py` | Skeletonize walls, trace the skeleton into polylines (graph walk from endpoints and junctions), simplify with Douglas–Peucker, optional snapping to horizontal and vertical. |
| `postprocess/portals.py` | Each portal blob -> principal axis -> one segment; cut wall polylines where a portal crosses them. |
| `postprocess/writer.py` | Write the .dd2vtt: `format`, `resolution` (70 px per square), `line_of_sight`, `portals`, `lights` (takes a list; empty until `postprocess/lights.py` exists in week 6), base64 PNG image. Pixel -> grid units, undoing the scale normalization. |
| `tests/test_postprocess.py` | **Round trip:** rasterize the demo map's .dd2vtt -> vectorize -> write -> rasterize again; the masks match closely (wall IoU > 0.9) and the portal count is the same. A doorless gap stays open after cleaning. |
| `tests/test_writer.py` | Output loads with `load_uvtt`; coordinates are in grid units; given lights are written with grid-unit positions and their `range`; no lights gives an empty list. |

The skeleton tracer is written by hand, so `skan` is not needed.

## Run

```bash
docker compose run --rm app python -m train.train --config train/configs/stage2_dungeondraft.toml
docker compose run --rm app pytest tests/test_postprocess.py -v
```

## Done when

- [ ] Stage 2 run finished; Dungeondraft validation scores logged next to stage 1 and Canny.
- [ ] Round-trip test passes on the demo map and on every Dungeondraft validation map.
- [ ] All tests pass.

## Report

- Training curves for stage 2 (fine-tuning), with the chosen checkpoint marked.

## Dependencies

None new: scikit-image and opencv-python-headless are already in from week 2.
