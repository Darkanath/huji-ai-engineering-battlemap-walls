# Week 4 · 10–16.11 · Pivot: Claude tracer, model comparisons, spec and plan

**Goal:** decide whether a large model can replace the trained one, and if so turn it into a
pipeline and a plan for the app.

This week was planned as "Dungeon Alchemist maps, fine-tune on real maps, mask -> .dd2vtt". On
13.11 the course staff allowed a large model in place of a trained one, and the week became the
pivot. The stage 2 fine-tuning run, the `da02`–`da06` maps and the mask-to-polyline
post-processing were dropped.

## You

- [x] Ask the course staff whether a large model may replace the trained one. *Allowed, 13.11.*
- [x] Import a traced map into Roll20. *13.11: `data/test/map-26x28.jpeg`, fog of war works;
      one mistake, an extra door inside the bathroom.*
- [ ] Read and approve the spec and the constitution
      (`specs/001-battlemap-tracer-app/spec.md`, `.specify/memory/constitution.md`).
- [x] No more real maps, except if testing needs one; cloud deployment optional, local first.
      *Decided 13.11.*
- [ ] Decide how many test-set maps to trace (PLAN.md, open questions).

## Code

| File | What |
| --- | --- |
| `llm/agent.py` *(done)* | The tool loop: `trace_map(image, map_size, cfg, client, views_dir)` sends the views, lets the model ask for crops, takes its answer, shows it back on an overlay, and returns a `Trace` (answer, cost, time, closing note). Limits per map from the config. |
| `llm/views.py` *(done)* | `render_view`: a map region with a labeled square grid, optionally with an answer drawn over it. |
| `llm/run.py` *(done)* | Batch runs and scoring: `python -m llm.run --maps ... --run NAME --model MODEL --effort EFFORT`. |
| `llm/configs/claude.toml` *(done)* | Model, effort, limits, views (quarters up front) and prices. |
| `postprocess/uvtt.py` *(done)* | `answer_to_uvtt`, `write_uvtt`: the tracer's answer -> .dd2vtt; arcs become polylines; light `range` from the tier table. |
| `tests/test_llm_agent.py`, `tests/test_llm_views.py`, `tests/test_uvtt_writer.py` *(done)* | The loop with a fake client, the views, and the writer. |
| `docs/results.md` *(done)* | The spike, tracer v1 (four models) and tracer v2 (quarters up front). |
| `docs/app-plan.md` *(done)* | The app plan: Sonnet draft, Opus deep pass, accept and download. |
| `specs/001-battlemap-tracer-app/spec.md` *(done)* | The feature spec, including map size worked out by the model. |
| `.specify/memory/constitution.md` *(done)* | Project principles. |
| `CLAUDE.md`, `docs/PLAN.md`, `README.md`, `docs/roadmap/` *(done)* | Rewritten around the tracer. |
| `specs/001-battlemap-tracer-app/plan.md`, `tasks.md` | The implementation plan and task list (`/speckit-plan`, `/speckit-tasks`). |

## Run

```bash
docker compose run --rm app pytest
docker compose run --rm app python -m llm.run --maps dd07_a dd06_a --run NAME --model MODEL --effort medium
```

## Done when

- [x] The tracer beats the stage-1 U-Net and Canny on the two reference maps. *(v2, wall
      boundary F1: Opus 0.989 / 0.881, Sonnet 0.960 / 0.664; U-Net 0.664 / 0.118; Canny 0.058 /
      0.133.)*
- [x] A traced map imports into Roll20.
- [x] Spec and constitution written; docs rewritten.
- [ ] Plan and tasks written for the app.
- [ ] The week's work committed (pipeline committed 13.11; spec, constitution and docs not yet).

## Report

- The pivot story: spike, v1, v2, with the comparison tables and what each step cost
  (about $3 in all).

## Dependencies

- `anthropic` (approved 13.11).
