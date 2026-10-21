# Week 8 · 8–14.12 · Test set run, error analysis, model card

**Goal:** the one and only test-set run, an honest error analysis, and the model card.

## You

- [ ] Time the manual Roll20 fixes on 3–5 test maps (the "Fix time" column).
- [ ] Workshop session 14.12: show the results and collect feedback.

## Code

| File | What |
| --- | --- |
| `eval/evaluate.py` | Run every model in the results table on the test split, **once**, for in-domain and hard sets separately. Save to `runs/test/`. |
| `eval/failure_gallery.py` | The worst test predictions by visibility IoU: image, ground truth and prediction side by side, saved as figures. |
| `notebooks/figures.ipynb` | Final figures: data summary, curves, learning progression, results tables, contact sheets. |
| `docs/results.md` | Final results tables (in-domain, hard), ablations, fix times, failure gallery with one line per failure. |
| `docs/model-card.md` | Model, training data and licensing, metrics, intended use, limitations (outdoor, photoreal, hex grids, multi-floor; light brightness comes from a tier table, not from the image). |

## Run

```bash
docker compose run --rm app python -m eval.evaluate --all-models --split test
docker compose run --rm app python -m eval.failure_gallery --split test
```

## Done when

- [ ] Test results recorded for every row of the results table, on both test splits.
- [ ] Failure gallery done, each failure with one sentence on why.
- [ ] Model card and results written.

## Report

- Results table (in-domain and hard), failure gallery, model card.

## Dependencies

None new. Jupyter for the notebook is **new, ask first** if needed; the figures can also be a
plain script (`eval/figures.py`).
