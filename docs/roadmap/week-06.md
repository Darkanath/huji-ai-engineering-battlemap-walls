# Week 6 · 24–30.11 · Results table from existing runs

**Goal:** one results table for the presentation, built from the runs already made. No new
paid runs (decided 13.11): the app is finished, and the measurements in `docs/results.md`
are the evaluation. Can start before 24.11.

What the table draws on:

- Both passes on the reference maps (`dd04_a` tavern, `dd06_a` mine, `dd07_a` castle,
  `dd04_d` no grid), with the castle repeat.
- The tracer v1 and v2 model comparisons (Haiku, Sonnet, Opus, Fable) on the castle and the
  mine.
- The Canny baseline and the stage-1 U-Net from weeks 2–3, as the comparison with the first
  approach.

## You

- [ ] *(optional)* Time the manual Roll20 fixes on two traced maps, a building and the mine,
      for a "minutes saved" line on the results slide.

## Code

| File | What |
| --- | --- |
| `docs/results.md` | A summary table at the top: per pass, wall boundary F1 and portal recall per map, cost and time per map, runs per cell; the first approach's rows beside it. Every number taken from an existing section. |

## Done when

- [ ] The summary table is in `docs/results.md`, each cell traceable to a run.
- [ ] Its weaknesses are written next to it: four maps, one to three runs per cell.

## Report

- The comparison table; a cost-per-map line; one building and the mine as before/after images.
