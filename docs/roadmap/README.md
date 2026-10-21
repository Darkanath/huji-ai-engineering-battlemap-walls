# Roadmap

One file per week. Open the file for the current week and work top to bottom: it lists every file
to create, the commands to run and what "done" means. The overall plan and the reasons behind it
are in [PLAN.md](../PLAN.md); the rules for labels are in [labeling-rules.md](../labeling-rules.md); what goes on each
real map (Dungeondraft and Dungeon Alchemist) is in [map-specs.md](../map-specs.md), and the maps
made so far are in [map-log.md](../map-log.md);
how the models are trained is in [training.md](../training.md).

| Week | Dates | Focus | File |
| --- | --- | --- | --- |
| 1 | 20–26.10 | Setup, rasterizer, labeling rules, first maps | [week-01.md](week-01.md) |
| 2 | 27.10–2.11 | Manifest, synthetic generator, metrics, Canny baseline | [week-02.md](week-02.md) |
| 3 | 3–9.11 | First U-Net on synthetic data | [week-03.md](week-03.md) |
| 4 | 10–16.11 | Dungeon Alchemist maps, fine-tune on real maps; mask -> .dd2vtt | [week-04.md](week-04.md) |
| 5 | 17–23.11 | End to end, visibility IoU. **Milestone: first Roll20 import** | [week-05.md](week-05.md) |
| 6 | 24–30.11 | Ablations, grid detection, final test set | [week-06.md](week-06.md) |
| 7 | 1–7.12 | Gradio app, ONNX, deploy. **Feature freeze 07.12** | [week-07.md](week-07.md) |
| 8 | 8–14.12 | Test set run, error analysis, model card | [week-08.md](week-08.md) |
| 9 | 15–23.12 | Slides, demo video, rehearsal. **Presentation 23.12** | [week-09.md](week-09.md) |

## How each week file works

- **You:** tasks only you can do (making maps in Dungeondraft and Dungeon Alchemist, Roll20, course
  admin).
- **Code:** modules to write, each with its test file. Every module that transforms data gets a
  pytest test (CLAUDE.md).
- **Run:** the commands, always through Docker Compose.
- **Done when:** the checklist that closes the week. Tick boxes as you go.
- **Report:** which exhibits for the training and validation report the week produces.
- **Dependencies:** packages the week needs. They are added only in that week, and only after
  you approve them. Anything not listed in CLAUDE.md is marked **new, ask first**.

## Project-wide decisions the roadmap relies on

- Configs are **TOML**, read with Python's built-in `tomllib`, so no YAML package is needed.
- Every dataset is written to disk with a seed per map and listed in `data/processed/manifest.csv`.
- Splits are by layout (`dd01_a` to `dd01_d` stay together) and are fixed by a seed.
- The test set is run **once**, in week 8, after the model is chosen.
- If a week slips, cut from the stretch items marked *(stretch)*, never from tests or the report.
- Items marked *(lights)* are light-source work. They come after the week 5 milestone and are cut
  next after the stretch items, never walls or portals. Light labels (rasterizer, generator,
  Dungeondraft and Dungeon Alchemist maps) are not marked: they are needed from week 2 so every run trains with 4
  classes.
