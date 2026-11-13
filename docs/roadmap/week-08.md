# Week 8 · 8–14.12 · Test set run, error analysis, system card

**Goal:** the one and only test-set run, an honest error analysis, and the system card.

## You

- [ ] **Approve the test-set run before it starts** (both profiles on every test map; the
      cost is stated when the test set's size is known).
- [ ] Time the manual Roll20 fixes on 3–5 test maps (the "Fix time" column).
- [ ] Workshop session 14.12: show the results and collect feedback.

## Code

| File | What |
| --- | --- |
| `eval/evaluate.py`, `llm/run.py` | Run every predictor in the results table on the test split, **once**, for in-domain and hard sets separately. Save to `runs/test/`. |
| `eval/failure_gallery.py` | The worst test results by wall boundary F1: image, ground truth and answer side by side, saved as figures. |
| `eval/figures.py` | Final figures: data summary, the first approach's curves and learning progression, results tables, cost per map. |
| `docs/results.md` | Final tables (real maps, in-domain test, hard test), fix times, failure gallery with one line per failure. |
| `docs/system-card.md` | What the system is: the models used and their versions, the data and its licensing, metrics, intended use, cost per map, privacy (images go to a third-party provider), limitations (caves, outdoor, photoreal, hex grids, multi-floor; light brightness from a tier table; results vary between runs). |

## Run

```bash
docker compose run --rm app python -m eval.evaluate --all-models --split test    # after approval
docker compose run --rm app python -m eval.failure_gallery --split test
```

## Done when

- [ ] Test results recorded for every row of the results table, on both test splits.
- [ ] Failure gallery done, each failure with one sentence on why.
- [ ] System card and results written.

## Report

- Results tables, failure gallery, system card.

## Dependencies

None new. A plotting package for `eval/figures.py` is **new, ask first**.
