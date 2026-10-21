# Week 4 · 10–16.11 · Dungeon Alchemist maps, fine-tune on real maps; mask -> .dd2vtt

**Goal:** the real-map set finished, the stage 2 model fine-tuned on it (Dungeondraft and Dungeon
Alchemist maps), and the post-processing that turns a predicted mask into a .dd2vtt. This is about half the engineering work, so it starts now.

## You

- [ ] **Before the stage 2 run:** 5 Dungeon Alchemist layouts × 4 variants, `da02`–`da06`, as
      specified in [map-specs.md](../map-specs.md). Save exports to
      `data/raw/dungeon_alchemist/original/`, convert their lights with `data.retier_lights`
      (add a rule for any new light asset), check each preview, and log them in
      [map-log.md](../map-log.md). That makes 19 real layouts in total.
- [ ] Rebuild the manifest, so the new maps get their splits.
- [ ] Retune the Canny baseline once on the complete real val split
      (`python -m eval.baseline_canny --retune`), then leave it frozen.
- [ ] Keep tracing test-set maps.

## Code

| File | What |
| --- | --- |
| `train/configs/stage2_real.toml` | Stage 2: start from the stage 1 checkpoint, real train split (Dungeondraft + Dungeon Alchemist), lower learning rate. |
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
docker compose run --rm app python -m train.train --config train/configs/stage2_real.toml
docker compose run --rm app pytest tests/test_postprocess.py -v
```

## Done when

- [ ] Stage 2 run finished; real validation scores (pooled and per tool) logged next to stage 1 and Canny.
- [ ] Round-trip test passes on the demo map and on every real validation map.
- [ ] All tests pass.

## Report

- Training curves for stage 2 (fine-tuning), with the chosen checkpoint marked.

## Dependencies

None new: scikit-image and opencv-python-headless are already in from week 2.
