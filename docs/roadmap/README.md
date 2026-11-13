# Roadmap

One file per week. Open the file for the current week and work top to bottom: it lists what to
build, the commands to run and what "done" means. The overall plan and the reasons behind it
are in [PLAN.md](../PLAN.md); the rules for labels are in [labeling-rules.md](../labeling-rules.md);
the real maps made so far are in [map-log.md](../map-log.md); every measurement is in
[results.md](../results.md).

**The plan changed on 13.11** (week 4): the course staff allowed a large model in place of a
trained one, and the Claude tracer replaced the U-Net. Weeks 1–4 are the record of the first
approach and the pivot, kept as written in `docs/history/roadmap/`. Weeks 4–9 are rewritten around the tracer and its
app. Task-level detail for the app lives in `specs/001-battlemap-tracer-app/` (spec, plan,
tasks); the week files point there instead of repeating it.

**Rewritten again on 13.11, after week 5:** the app is the project's deliverable and is built,
tested and imported into Roll20. No model is trained and there is no held-out test set; what is
left is a results table from the runs already made, polish, the write-up and the
presentation (weeks 6–9). No more paid evaluation runs.

| Week | Dates | Focus | File |
| --- | --- | --- | --- |
| 1 | 20–26.10 | Setup, rasterizer, labeling rules, first maps | [history/roadmap/week-01.md](../history/roadmap/week-01.md) |
| 2 | 27.10–2.11 | Manifest, synthetic generator, metrics, Canny baseline | [history/roadmap/week-02.md](../history/roadmap/week-02.md) |
| 3 | 3–9.11 | First U-Net on synthetic data (last week of the first approach) | [history/roadmap/week-03.md](../history/roadmap/week-03.md) |
| 4 | 10–16.11 | **Pivot:** Claude tracer, model comparisons, .dd2vtt writer, spec and plan | [history/roadmap/week-04.md](../history/roadmap/week-04.md) |
| 5 | 17–23.11 | The app. **Milestone: a file from the app imports into Roll20** | [week-05.md](week-05.md) |
| 6 | 24–30.11 | Results table from existing runs (no new paid runs) | [week-06.md](week-06.md) |
| 7 | 1–7.12 | Polish from trying the app, demo setup. **Feature freeze 07.12** | [week-07.md](week-07.md) |
| 8 | 8–14.12 | System card, failure gallery, exhibits, demo video | [week-08.md](week-08.md) |
| 9 | 15–23.12 | Slides, demo video, rehearsal. **Presentation 23.12** | [week-09.md](week-09.md) |

## How each week file works

- **You:** tasks only you can do (Roll20, approving paid runs, tracing test maps, course admin).
- **Code:** what to build, each with its test file. Every module that transforms data gets a
  pytest test (CLAUDE.md).
- **Run:** the commands, always through Docker Compose.
- **Done when:** the checklist that closes the week. Tick boxes as you go.
- **Report:** which exhibits for the presentation the week produces.
- **Dependencies:** packages the week needs. They are added only in that week, and only after
  you approve them. Anything not listed in CLAUDE.md is marked **new, ask first**.

## Project-wide decisions the roadmap relies on

- Configs are **TOML**, read with Python's built-in `tomllib`, so no YAML package is needed.
- Model names, effort, limits and prices live in `llm/configs/claude.toml`, never in code.
- Tests never make a paid call; they use the fake client in `tests/conftest.py`.
- A paid run larger than a few maps is approved by you first, with its estimated cost.
- Every predictor is scored the same way (`data/rasterize.py` + `eval/metrics.py`, 32 px per
  square), and every result goes in `docs/results.md` with its run name, cost and sample size.
- There is no held-out test set (dropped 13.11). Third-party maps are used only to try and demo
  the app; they are never scored, committed or redistributed.
- The first approach's code was removed on 13.11 (in git history up to `7a5979d`); its results stay
  in `docs/results.md`.
- If a week slips, cut from the items marked *(stretch)*, never from tests or the report.
