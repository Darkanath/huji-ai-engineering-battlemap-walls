# Roadmap

One file per week. Open the file for the current week and work top to bottom: it lists what to
build, the commands to run and what "done" means. The overall plan and the reasons behind it
are in [PLAN.md](../PLAN.md); the rules for labels are in [labeling-rules.md](../labeling-rules.md);
the real maps made so far are in [map-log.md](../map-log.md); every measurement is in
[results.md](../results.md).

**The plan changed on 13.11** (week 4): the course staff allowed a large model in place of a
trained one, and the Claude tracer replaced the U-Net. Weeks 1–3 are the record of the first
approach and are left as they were written. Weeks 4–9 are rewritten around the tracer and its
app. Task-level detail for the app lives in `specs/001-battlemap-tracer-app/` (spec, plan,
tasks); the week files point there instead of repeating it.

| Week | Dates | Focus | File |
| --- | --- | --- | --- |
| 1 | 20–26.10 | Setup, rasterizer, labeling rules, first maps | [week-01.md](week-01.md) |
| 2 | 27.10–2.11 | Manifest, synthetic generator, metrics, Canny baseline | [week-02.md](week-02.md) |
| 3 | 3–9.11 | First U-Net on synthetic data (last week of the first approach) | [week-03.md](week-03.md) |
| 4 | 10–16.11 | **Pivot:** Claude tracer, model comparisons, .dd2vtt writer, spec and plan | [week-04.md](week-04.md) |
| 5 | 17–23.11 | The app. **Milestone: a file from the app imports into Roll20** | [week-05.md](week-05.md) |
| 6 | 24–30.11 | Full evaluation run on the real maps, final test set | [week-06.md](week-06.md) |
| 7 | 1–7.12 | App polish, request log, demo setup. **Feature freeze 07.12** | [week-07.md](week-07.md) |
| 8 | 8–14.12 | Test set run, error analysis, system card | [week-08.md](week-08.md) |
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
- Tests never make a paid call; they use the fake client from `tests/test_llm_agent.py`.
- A paid run larger than a few maps is approved by you first, with its estimated cost.
- Every predictor is scored the same way (`data/rasterize.py` + `eval/metrics.py`, 32 px per
  square), and every result goes in `docs/results.md` with its run name, cost and sample size.
- The test set is run **once**, in week 8, after the harness is frozen.
- `train/`, the synthetic generator and the Colab notebook are frozen: no further work.
- If a week slips, cut from the items marked *(stretch)*, never from tests or the report.
