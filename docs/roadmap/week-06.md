# Week 6 · 24–30.11 · Full evaluation run on the real maps, final test set

**Goal:** the comparison table on all 34 real maps (Canny, the stage-1 U-Net, both tracer
profiles), map-size accuracy measured, and the test set frozen.

## You

- [ ] **Approve the full evaluation run before it starts:** all 34 real maps with both
      profiles, about $2.50 on Sonnet plus $9 on Opus.
- [ ] Time the manual Roll20 fixes on 2–3 traced maps (a building and a cave), for the "Fix
      time" column in `docs/results.md`.
- [ ] Finalize the test set: published maps, split into **in-domain** (Dungeondraft-like or
      Dungeon Alchemist-like) and **hard** (outdoor, photoreal). Trace them in Dungeondraft
      following "Hand-tracing the test set" in the labeling rules, swap the original image in
      with `data/attach_image.py`, and record them in `data/raw/test/test_maps.csv` and
      `docs/map-log.md`. Third-party maps never leave `data/raw/test/`.

## Code

| File | What |
| --- | --- |
| `eval/baseline_canny.py` | Retune once on the real maps (`--retune`), then leave it frozen. |
| `llm/run.py` | Run a whole split or dataset; record per map the scores, the cost, the time, and whether the model's map size matched the true one. Resume a run that stopped partway without paying twice. |
| `eval/report.py` | Collect the runs into the results table: per predictor, development maps (`dd06`, `dd07`) apart from the rest, buildings apart from caves. |
| `tests/test_report.py` | The table is built from saved per-map scores; a map missing from one run is reported, not silently dropped. |
| `eval/visibility.py`, `tests/test_visibility.py` *(stretch)* | Visibility IoU: ~100 seeded viewpoints per map, visibility polygon with predicted and with true walls. |
| `eval/metrics.py` *(stretch)* | Light F1 (match within 0.5 squares) and tier accuracy. |

## Run

```bash
docker compose run --rm app python -m eval.baseline_canny --retune
docker compose run --rm app python -m eval.evaluate --predictor canny --split all
docker compose run --rm app python -m eval.evaluate --predictor unet --checkpoint runs/r1_stage1_synthetic/best.pt --split all
docker compose run --rm app python -m llm.run --profile quick --run eval_quick    # after approval
docker compose run --rm app python -m llm.run --profile deep --run eval_deep      # after approval
docker compose run --rm app python -m eval.report
```

The exact flags are settled when the code is written; the commands above show the intent.

## Done when

- [ ] All four predictors scored on the 34 real maps; table in `docs/results.md` with cost,
      time and the number of runs per cell.
- [ ] Map-size accuracy measured; SC-009's 80% target in the spec confirmed or revised.
- [ ] The reference-map thresholds in the spec (SC-003, SC-004) checked against repeat runs.
- [ ] Test set frozen and traced. **No test-set runs yet.**
- [ ] All tests pass.

## Report

- The comparison table and the cost per map; first Roll20 fix times.

## Dependencies

- `shapely` only if visibility IoU is built (agreed in CLAUDE.md as a stretch).
