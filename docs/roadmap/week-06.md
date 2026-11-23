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

## Added 23.11: the chunked pass (feature 002)

The owner decided on 23.11 to build a third pass, chunked tracing with parallel agents and an
orchestrator, as the multi-agent exhibit (`specs/002-chunked-map-tracing/`, constitution
2.1.0). Its code is built and tested with fakes. It changes the 13.11 "no new paid runs"
decision for this feature only: each run below is the owner's, approved with its printed
estimate first.

- [ ] One live chunked pass in the app on the castle, Sonnet agents (about $0.29), and its
      file imported into Roll20 (tasks T037; quickstart step 4).
- [ ] Reference runs: `python -m llm.run --reference --chunked --agents sonnet` (about $1.2),
      then `--agents haiku` (about $0.3), and `--agents opus` (about $3.8) only if wanted for
      the slides (tasks T040-T042).
- [ ] Results recorded in `docs/results.md` and the measured figures set in the config
      (T043-T044).

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
