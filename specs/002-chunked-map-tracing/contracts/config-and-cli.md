# Contract: Config and Command Line

## `llm/configs/claude.toml`: new tables

```toml
# The chunked pass (specs/002-chunked-map-tracing/): the map is split into up to 4 x 4 chunks,
# each traced by its own agent at the same time; the answers are merged by fixed rules, then an
# orchestrator model reviews the strips along the borders between chunks. The user picks the
# agents' model; the orchestrator's follows from it (constitution 2.1.0).
[chunked]
default_agents = "sonnet"
overlap_squares = 1        # each chunk also sees and traces this far into its neighbours
max_per_side = 4           # at most 4 x 4 = 16 chunks; larger maps get larger chunks
max_parallel = 4           # agents running at the same time

# One entry per selector choice. ESTIMATE figures are replaced after the measured run
# (research.md R5, R13); `estimate = false` then drops the "estimate" word on the button.
[chunked.agents.haiku]
core_squares = 7                    # the model's part size: 16 parts on 25 x 25
name = "claude-haiku-5-5"
label = "Haiku 5.5"
effort = "medium"
max_tokens = 16000
fallbacks = false                   # not offered for Haiku
orchestrator = "sonnet"
deadline_s = 180                    # the whole pass
max_cost_usd = 1.0                  # the whole map; chunks not started yet are skipped past it
expected_seconds_per_chunk = 30     # ESTIMATE
expected_cost_per_chunk_usd = 0.005 # ESTIMATE
estimate = true

[chunked.agents.sonnet]
core_squares = 13                   # 4 parts on 25 x 25
name = "claude-sonnet-5-5"
label = "Sonnet 5.5"
effort = "medium"
max_tokens = 16000
fallbacks = true
orchestrator = "sonnet"
deadline_s = 180
max_cost_usd = 2.5
expected_seconds_per_chunk = 25     # ESTIMATE
expected_cost_per_chunk_usd = 0.06  # ESTIMATE
estimate = true

[chunked.agents.opus]
core_squares = 13
name = "claude-opus-5-5"
label = "Opus 5.5"
effort = "medium"
max_tokens = 16000
fallbacks = true
orchestrator = "opus"
deadline_s = 420
max_cost_usd = 6.0
expected_seconds_per_chunk = 60     # ESTIMATE
expected_cost_per_chunk_usd = 0.20  # ESTIMATE
estimate = true

[chunked.limits]                    # per chunk agent; the single session's [limits] are unchanged
max_turns = 16
max_views = 8
max_submissions = 2
max_cost_usd = 0.75

[chunked.review]                    # the orchestrator's seam review
strip_squares = 1.0                 # it may change lines within this distance of a seam
max_turns = 10
max_views = 6
max_submissions = 2
max_cost_usd = 0.75
expected_seconds = { sonnet = 20, opus = 45 }        # ESTIMATE, by orchestrator
expected_cost_usd = { sonnet = 0.05, opus = 0.15 }   # ESTIMATE, by orchestrator

[chunked.merge]
join_tolerance_squares = 0.3        # wall ends on a seam closer than this are joined
min_piece_squares = 0.05            # clipped wall pieces shorter than this are dropped
```

`[size_step]` gains `expected_seconds = 8` (used only for the chunked button's time).

Validated by `app/config.py` (`ChunkedSettings`, [data-model.md](../data-model.md)); an invalid
table fails app start-up with the pydantic error, as the other tables do. A test keeps
`[prices]` covering every model named here. `llm/orchestrator.load_chunked_config(agents)`
returns a plain dict for the tool loops: the agents' model as `cfg["model"]`,
`[chunked.limits]` as `cfg["limits"]`, and the orchestrator's model and `[chunked.review]` under
`cfg["review"]`.

## `python -m llm.run`: new flags

```
python -m llm.run --reference --chunked [--agents sonnet] [--run NAME] [--yes] [--redo]
python -m llm.run --image runs/test-maps/big.png --squares 50 50 --chunked --agents haiku
```

- `--chunked`: trace each map with the orchestrator. `--agents haiku|sonnet|opus` (default
  `[chunked].default_agents`). `--profile` is not used with `--chunked`. `--model`/`--effort`
  override the agents' model as today (the orchestrator is unchanged).
- Before any call it prints: maps, chunks per map, estimated cost per map (chunks x per-chunk
  cost + review) and in total, and asks (skip with `--yes`).
- Default run folder: `runs/<YYYYMMDD-HHMMSS>_chunked_<agents>/`.
- Per map: `merged.json` (rule merge), `answer.json` (final), `<map>.dd2vtt`, `preview.jpg`,
  `trace.json` (totals, per-chunk and review summary), `merge.json` (MergeReport),
  `review/` (`trace.json`, `responses.json`, `submission.json`, `views/`) and `chunks/<i>/`
  (`trace.json`, `responses.json`, `answer.json`, `views/`).
- `summary.csv` row: the existing columns plus `method` (`chunked`), `agents`, `orchestrator`,
  `chunks`, `chunks_failed`, `chunks_skipped`, `review` (state), `review_cost_usd`, the scores of
  the final answer under the usual names and of the rule-merged answer as `merged_<name>`, and
  `merge.seam_checks` of both (`seam_gap_ends`, `duplicate_portals`, `duplicate_lights`, and
  the same with `merged_`) for SC-003.
- Resuming and `--redo` work as today (marker: the map's `trace.json`).
