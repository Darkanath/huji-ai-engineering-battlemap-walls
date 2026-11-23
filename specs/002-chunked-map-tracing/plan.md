# Implementation Plan: Chunked Map Tracing

**Branch**: `002-chunked-map-tracing` | **Date**: 2026-11-23 (revised after `/speckit-clarify` and constitution 2.1.0) | **Spec**: [spec.md](spec.md)

**Input**: Feature specification from `specs/002-chunked-map-tracing/spec.md`

## Summary

A third pass in the app, and a `--chunked` mode in the batch tool. The map is split into up to
4 x 4 overlapping chunks. Each chunk is traced by its own agent: the existing, measured tool
loop, run on a window of the map with the whole map as an outlined overview. Up to four agents
run at the same time, under one deadline and one cost limit. The user picks the agents' model
(Haiku, Sonnet or Opus) with a selector.

The orchestrator first merges the answers by fixed rules. Each chunk keeps what lies in its
own core area, walls cut at the seams are snapped and joined, and portals and lights are kept
once by ownership. Then an orchestrator model (Sonnet for Haiku or Sonnet agents, Opus for
Opus agents) reviews only the strips along the seams, at close zoom, and its corrections
replace what is inside those strips. The result is exported through the existing export.

While the pass runs, the page shows the chunk layout, each agent's state and the review. After
it, a table shows one row per agent plus the review. This is what the owner presents as
multi-agent orchestration.

Planning found that today's quarter views already show the 25 x 25 reference maps above their
own resolution. So on these maps chunking buys focus, not detail ([research.md](research.md)
R1); the measured run (US3) decides what can be claimed about accuracy.

## Technical Context

**Language/Version**: Python 3.12 (Ubuntu 24.04 default)

**Primary Dependencies**: already installed: `anthropic`, `gradio`, `pydantic` v2, `Pillow`,
`numpy`, `opencv-python-headless` (scoring). Standard library `concurrent.futures` and
`threading`. **No new dependency**: clipping, snapping and joining are rectangles and
polylines in plain Python (research R4).

**Storage**: none new. In-memory session state as today; batch runs write under `runs/`.

**Testing**: `pytest` with the scripted `FakeClient`. Order-dependent orchestrator tests use
`max_parallel = 1`. Parallel tests use a small routing fake in the new test file, which picks
each agent's script by the window named in its first request. The shared fake is not changed.
`ruff check`, `ruff format --check`.

**Target Platform**: the owner's laptop under Docker Compose; browser at `http://localhost:7860`.

**Project Type**: local single-user web app plus a command-line evaluation tool (unchanged).

**Performance Goals** (estimates until US3, research R5):

| Agents | 25 x 25 (4 chunks + review) | 50 x 50 (16 chunks + review) |
| --- | --- | --- |
| Haiku | ~$0.07, ~50 s | ~$0.13, ~140 s |
| Sonnet | ~$0.29, ~45 s | ~$1.01, ~120 s |
| Opus | ~$0.95, ~105 s | ~$3.35, ~285 s |

SC-004 (at most twice the single session's time, same model): Sonnet ~45 s against 2 x 25 s.
Preview refresh while running: once a second, as now.

**Constraints**: only model calls leave the laptop; no paid call in tests; nothing sent before
validation; expected time and cost before the click, actual after; per-choice whole-pass
deadline and cost limit, per-chunk and review limits, all in config; single-session passes
unchanged in what they send.

**Scale/Scope**: one user. New modules: `llm/merge.py`, `llm/review.py`, `llm/orchestrator.py`,
`app/progress.py`. Changed: `llm/agent.py`, `llm/views.py`, `llm/run.py`, `app/config.py`,
`app/domain.py`, `app/tracer.py`, `app/service.py`, `app/render.py`, `app/errors.py`,
`app/main.py`, the config, and docs. About three to four weeks of work for one person; the
presentation is on 2026-12-23 (see Delivery order for what to cut if time runs short).

## Constitution Check

*GATE: Must pass before Phase 0 research. Re-check after Phase 1 design.*

Checked against constitution **v2.1.0** (commit `faddcb2`).

| Principle | Gate | Result |
| --- | --- | --- |
| I. Python only, laptop, Docker | All new code is Python; UI changes are Gradio components (radio, button, dataframe); threads, no GPU; only model calls leave the laptop | Pass |
| II. Paid calls visible, bounded, approved | The chunked button shows chunk count, agents' model, expected time and cost for this map and choice, marked "estimate" until measured; status line and table show actual time and cost (agents + review + size step); notice and validation unchanged; per-choice deadline and cost limit, per-chunk and review limits in config; tests use fakes; the batch tool prints chunks x cost + review and asks; each US3 run is approved by the owner | Pass |
| III. Measured, not assumed | Chunk prompt, windowed views and the review are tracing changes, so each agents choice is scored on the reference maps before any accuracy claim, with the rule-merged and reviewed answers scored from the same run; results in `docs/results.md` with run name, cost and sample size; single-session path unchanged so its scores stay valid; a no-model test shows the merge loses nothing against labels | Pass |
| IV. Tested and documented | Merge, apply-review and layout are pure and tested; tracer, review, orchestrator and service tested with fakes; every failure kind tested for a chunk and for the review; docstrings everywhere; `ruff` clean; `main.py` only wires controls | Pass |
| V. Simple, scoped for one person | Reuses `trace_map`, `_request`, `Trace`, `render_view`, `answer_to_uvtt`, `answer_to_fractions`, `score_row`; no new dependency; no "retry failed chunks only"; the new complexity (agents, review, selector) is what the owner asked for, to present multi-agent orchestration, and it adds a pass without changing the two that exist | Pass |
| Domain: Models (2.1.0) | Single-session profiles stay `quick` (Sonnet) and `deep` (Opus); Haiku is offered only in the chunked pass's selector; orchestrator pairing Sonnet/Sonnet/Opus as required; models, pairing, expected figures in config; figures marked as estimates until measured | Pass |
| Domain: other | Four classes; one portal type; lights from tiers; 70 px per square export; any map size (layout tested 1 x 1 to 200 x 200); map size worked out once, inside the pass the user started; typed size wins | Pass |

No violations; Complexity Tracking is empty.

**Re-check after Phase 1 design**: still passing. Watch during implementation:

- `trace_map(window=None)` must send exactly what it sends today (guard test).
- The review may only change its strips (`apply_review` guarantee, tested).
- Expected figures stay marked as estimates until US3; `CLAUDE.md` (Models, Repo layout) and
  `docs/PLAN.md` are updated in the change that adds the pass.

## Project Structure

### Documentation (this feature)

```text
specs/002-chunked-map-tracing/
├── spec.md
├── plan.md              # this file
├── research.md          # R1-R13
├── data-model.md
├── quickstart.md
├── contracts/
│   ├── config-and-cli.md   # [chunked] tables, llm.run --chunked --agents
│   ├── orchestrator.md     # trace_map(window), render_view, merge, review, orchestrator
│   └── app.md              # run_pass, service, errors, render, page
├── checklists/requirements.md
└── tasks.md             # /speckit-tasks
```

### Source Code (repository root)

```text
llm/
├── agent.py          # + window: CHUNK_SYSTEM, outlined overview, crops kept in the window
├── views.py          # + render_view(outline=..., strips=...)
├── merge.py          # NEW: clipping, ownership, seams, snap and join, apply_review
├── review.py         # NEW: the orchestrator model's seam review (tool loop)
├── orchestrator.py   # NEW: chunk_layout, load_chunked_config, trace_chunks
├── run.py            # + --chunked --agents, per-chunk and review folders, merged_* scores
└── configs/claude.toml   # + [chunked], [chunked.agents.*], [chunked.limits], [chunked.review], [chunked.merge]

app/
├── config.py         # + ChunkedSettings, AgentSettings, ReviewSettings; SizeStep.expected_seconds
├── domain.py         # + PassKind.chunked, AgentChoice, ChunkState, ReviewState, ChunkReport, ReviewReport
├── progress.py       # NEW: ChunkBoard
├── tracer.py         # + chunked branch in run_pass; chunk and review logging
├── service.py        # + agents and board on Session, set_agents, labels, progress_line, agent_table
├── errors.py         # + partial_message, SEAMS_NOT_CHECKED, short reasons
├── render.py         # + chunk_overlay; untraced outlines
└── main.py           # + radio, third button, note, board while running, agent table

tests/
├── test_llm_merge.py          # NEW
├── test_llm_review.py         # NEW
├── test_llm_orchestrator.py   # NEW (with the routing fake)
├── test_llm_agent.py          # + window cases, unchanged-request guard
├── test_llm_views.py          # + outline, strips
├── test_llm_run.py            # + --chunked
├── test_app_config.py         # + [chunked] validation, expected figures
├── test_app_progress.py       # NEW
├── test_app_tracer.py         # + chunked: success, partial, all failed, review failed, each kind
├── test_app_service.py        # + selector, labels, board, agent table, messages
└── test_app_render.py         # + chunk_overlay, untraced outlines

docs/results.md, docs/PLAN.md, CLAUDE.md
```

**Structure Decision**: the existing layout. Orchestrator, merge and review live in `llm/`
beside the tool loop, because the app and the batch tool both use them; `app/` adds the pass,
its selector, progress, table and messages.

## Delivery order

1. **US1 (P1), core**: `merge.py` and `chunk_layout` (pure, test first, including the
   label-cut test), `trace_map(window)` and `render_view(outline)`, then `trace_chunks` without
   the review. Done when a fake four-agent run gives one valid file.
2. **US1, review**: `review.py`, `apply_review`, `render_view(strips)`, wired into
   `trace_chunks`. Done when a fake run with a reviewer changes only the strips.
3. **US2 (P2)**: config and settings, domain, `run_pass` branch, `ChunkBoard`, service,
   errors, render, page (radio, button, board, table). Done when quickstart step 3 passes and
   the owner's live run (step 4) works.
4. **US3 (P3)**: `llm.run --chunked --agents`; the owner approves and runs the evaluations;
   results and measured figures recorded; docs updated.

If time runs short before 2026-12-23, keep steps 1, 3 and the Sonnet run of step 4. The
review (step 2) is required by spec FR-020, so it is not dropped silently: shipping without it
needs the owner to amend FR-020 first (for example, "MUST review when enabled in
configuration"). The code is wired so the pass still works without a review
(`review.state = skipped`, with the "borders not checked" message), which keeps that option open.

## Risks

- **Rate limits with four agents at once.** A 429 fails one chunk (a partial result), not the
  pass. Lower `max_parallel` if it happens.
- **The reviewer drops correct lines in a strip.** It must resubmit everything in the strips,
  and the JSON listing of what is there makes copying easy. SC-009 measures it (reviewed vs
  rule-merged, same run). If it lowers scores, narrow `strip_squares` or tighten the review
  prompt, then re-score.
- **Opus on a large map is slow** (~285 s at 16 chunks). The button states it before the click.
- **Chunking may not beat the single session on 25 x 25 maps** (R1). That is a valid result to
  present; the orchestration still works, and the larger-map case can be shown on a
  third-party test map (not scored).
