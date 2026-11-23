# Research: Chunked Map Tracing

Decisions taken while planning, each with its reason and the alternatives rejected. Facts about
the current code were checked against the repo on 2026-11-23; numbers come from
`docs/results.md` (13.11: v1 comparison with Haiku, v2 harness, and the reference run
`runs/20261113-134942_quick/`, `runs/20261113-135137_deep/`). Revised the same day after the
clarification session (chunk cap, model selector, seam review, agent table) and constitution
2.1.0.

## R1. What chunking can and cannot buy on the reference maps

**Finding**: all four reference maps are 25 x 25 squares at 70 px per square (1750 px). The
single-session tracer sends the whole map plus four quarters of 13.5 squares, each scaled to
1300 px: about 96 px per square, already **above** the image's own 70. A 2 x 2 chunk view
(about 13.5 squares with its margin) is about the same: no more real detail.

**Decision**: chunking is planned and measured as a gain in **focus**, not resolution, on maps of
this size: each agent has about a quarter of the map, its own budget of closer views and
submissions, and a short conversation. The 13.11 run shows why that may matter: the fast pass
asked for **zero** extra views on every map and found **no** doors on the tavern (`dd04_a`, 0 of
23) or the castle (`dd07_a`, 0 of 17). On larger maps (50 x 50 at 70 px: a quarter gets about
50 px per square) chunking also adds resolution.

**Consequence**: spec FR-002 says "never less than the image's own pixels per square, or the
view cap"; SC-001 names the cave map `dd06_a`. Whether focus helps is what User Story 3
measures; the presentation claims an accuracy gain only after that run.

**Alternatives considered**: chunks small enough to beat the quarters' 96 px per square (3 x 3
or 4 x 4 on 25 x 25): above 70 px per square the extra pixels are interpolation, and 9 to 16
agents cost 2 to 4 times as much for no new detail.

## R2. Chunk layout, with the 4 x 4 cap

**Decision**: split each side evenly. With `core_squares` = C (default 13) and `max_per_side` =
4 (spec clarification: at most 16 chunks), a map of W x H squares gets
`nx = min(ceil(W / C), 4)` columns and `ny = min(ceil(H / C), 4)` rows. The cores are equal
slices (`W / nx` by `H / ny`, not necessarily whole squares) and **partition** the map: every
point lies in exactly one core (half-open intervals, the last closed at the map edge). Each
chunk's **window** is its core grown by `overlap_squares` (default 1) on every side with a
neighbour, clipped to the map.

| Map | Chunks | Core |
| --- | --- | --- |
| 13 x 13 or smaller | 1 | whole map, no seams, no review |
| 25 x 25 (reference) | 2 x 2 | 12.5 x 12.5 |
| 35 x 20 (a test map) | 3 x 2 | 11.7 x 10 |
| 50 x 50 | 4 x 4 | 12.5 x 12.5 |
| 200 x 200 | 4 x 4 (capped) | 50 x 50; shown at the 1300 px view cap, below native detail |

**Rationale**: equal slices avoid a thin last strip; the partition makes the merge rule simple
(R4); the cap bounds cost and time per click whatever the map size.

**Alternatives considered**: a fixed 2 x 2 for every map: does not scale. Content-aware cuts
(along empty floor): needs a model or a heuristic, and the seam review (R6) handles the seams.

**Revised 23.11 after the first live runs (T037):** the part size is per model
(`[chunked.agents.<choice>].core_squares`): Haiku 7 squares (16 parts on 25 x 25, four agents
at a time, so about four rounds), Sonnet and Opus 13. The 16-part cap is unchanged, so on maps
larger than about 28 x 28 Haiku's parts grow as Sonnet's do. Haiku on 25 x 25: about $0.13 and
140 s (estimate); its live 4-part runs cost $0.07 in 54 s.

## R3. How a chunk agent works: reuse `trace_map` with a window

**Decision**: add an optional `window` (a box in whole-map squares) to `llm.agent.trace_map`.
With no window the loop is unchanged byte for byte (a test compares the first request with the
one recorded before the change), so existing scores stay valid. With a window:

- System prompt `CHUNK_SYSTEM`: the same coordinate and labeling sections as `SYSTEM` (built from
  shared constants), with a different "How to work": you trace one part of a larger map, in the
  whole map's coordinates; trace everything inside your window up to its edge, including the
  margin a neighbour also traces; nothing outside it.
- Opening message: a small overview of the whole map with the window outlined, then the window
  at full zoom, then the intro naming the window and its core. No quarters.
- `view_region` crops are clamped to the window; the overlay after `submit_answer` shows the
  window.
- Limits from `[chunked.limits]`, smaller than the single session's.

`render_view` already labels the grid in whole-map squares for any box, so no coordinate
translation exists anywhere (FR-005). It gets one optional argument, `outline`.

**Alternatives considered**: crop the image and trace the crop as a small map, then shift
coordinates (loses the overview and invites off-by-overlap bugs); a new agent loop (duplicates
about 150 tested lines).

## R4. Rule-based merge: core ownership, then snap and join (no model call)

**Decision**, in `llm/merge.py`, pure functions:

1. Arcs become polylines first (`postprocess.uvtt.arc_points`).
2. Each chunk's walls are clipped to its **core** (Liang-Barsky per segment, plain Python);
   pieces shorter than `min_piece_squares` (0.05) are dropped. A wall crossing a seam is now cut
   exactly on the seam, from both sides.
3. A portal belongs to the chunk whose core holds its midpoint, a light to the chunk whose core
   holds its position; each chunk keeps only what it owns. Duplicates in the overlap disappear
   by construction, with no distance matching, and the output is deterministic (FR-008).
4. Polyline ends on a seam are grouped when within `join_tolerance_squares` (0.3) of each other
   and moved to their mean, which stays on the seam.
5. Where exactly two ends share a point, the two polylines are concatenated. Three or more (a
   four-chunk corner) stay separate, sharing the point.
6. A `MergeReport` counts clipped, dropped, snapped and joined items, and portals and lights
   kept or dropped per chunk.

The merge never extends or invents a wall; gaps at doors survive because each agent leaves them
and clipping does not close gaps.

**Alternatives considered**: deduplicate by distance across the overlap (more thresholds, less
predictable); `shapely` (agreed in CLAUDE.md but not installed, not needed for rectangles and
polylines; constitution V).

## R5. Model choice and pairing (constitution 2.1.0)

**Decision**: config table `[chunked.agents.<choice>]` for `haiku`, `sonnet`, `opus`, each with
the model fields the tool loop needs (`name`, `label`, `effort`, `max_tokens`, `fallbacks`),
`orchestrator` (`"sonnet"` for haiku and sonnet, `"opus"` for opus), the whole-pass
`deadline_s` and `max_cost_usd`, and expected per-chunk figures. `[chunked].default_agents =
"sonnet"`. The orchestrator's model fields come from the `[chunked.agents.<orchestrator>]`
entry, so each model is described once. The map-size step stays on `[size_step]` (Opus), once
per map, before chunking.

Expected figures, marked as estimates in the config until User Story 3 measures them
(constitution: "estimates until measured"):

| Agents | Per chunk | 25 x 25 (4 chunks + review) | 50 x 50 (16 chunks + review) | Basis |
| --- | --- | --- | --- | --- |
| Haiku | ~$0.005, ~30 s | ~$0.07, ~50 s | ~$0.13, ~140 s | Haiku whole map $0.01 / 31-36 s (13.11 v1) |
| Sonnet | ~$0.06, ~25 s | ~$0.29, ~45 s | ~$1.01, ~120 s | Sonnet whole map $0.07-0.10 / 14-29 s |
| Opus | ~$0.20, ~60 s | ~$0.95, ~105 s | ~$3.35, ~285 s | Opus whole map $0.25-0.41 / 48-104 s |

Review: ~$0.05 / 20 s on Sonnet, ~$0.15 / 45 s on Opus. Times assume 4 agents at once. Limits
per choice: `deadline_s` haiku 180, sonnet 180, opus 420; `max_cost_usd` haiku 1, sonnet 2.5,
opus 6, each above the 16-chunk estimate so the cap never skips chunks on an ordinary run.

Haiku: no server-side fallback (the tool loop already skips it for Haiku); it was weak on caves
on 13.11, which the chunked run will show either way. Fable is not offered (constitution:
comparisons only, via `--model`).

**Alternatives considered**: reuse `[profiles.quick]` / `[profiles.deep]` and add
`[profiles.haiku]` (would make Haiku look like a fourth single-session pass and break
`Settings.profiles`' two-key rule); a free choice of orchestrator (spec fixes the pairing).

## R6. The seam review: what the orchestrator model does

**Decision** (spec FR-020): `llm/review.py`, a tool loop of its own in the same style as
`trace_map` (reusing `_request`, `Trace`, `render_view`, `answer_to_uvtt`):

- **Strips.** Every internal core border is a seam: vertical lines at the column borders, full
  map height; horizontal at the row borders, full width. Each seam's strip is the band
  `strip_squares` (default 1) either side of it. A 2 x 2 layout has 2 strips; 4 x 4 has 6.
- **Opening message.** `REVIEW_SYSTEM` explains the task: these are the borders where separate
  agents' work was joined; check each strip against the image; fix walls that are broken,
  doubled, misjoined or missing there, and doors or lights that are wrong or doubled. Then, per
  strip, crops along it in pieces of about 8 squares (so each square gets real zoom), with the
  merged answer drawn on them, then a text listing (JSON) of the merged walls, portals and
  lights that touch the strips, so the model can copy what is right.
- **Tools.** `view_region` (crops clamped to the strips' union; overlay optional; limit
  `max_views`) and `submit_corrections` (walls, arcs, portals, lights: the **complete** content of
  all strips, in whole-map squares). After a submission it sees the corrected strips drawn and
  may resubmit (limit `max_submissions`, default 2). Limits in `[chunked.review]`.
- **Apply** (`merge.apply_review`, pure): remove from the merged answer everything inside the
  strips (walls clipped to the outside of the strips' union; portals and lights by position),
  add the submission clipped to the strips, then snap and join ends on the strip edges with the
  same rule as R4. Nothing outside the strips can change (FR-020, edge case "moves a line out
  of its strip"). The report counts walls, portals and lights removed and added.
- **Failure.** Any exception, refusal, limit or deadline with no submission keeps the
  rule-merged answer, sets `seams_reviewed = False`, and the user is told the borders were not
  checked. A submission followed by an error is kept, as in the tracer.
- **Budget.** It runs after the agents, inside the same pass deadline and cost limit; if the
  agents left no time or budget for it, it is skipped (same message).

**Rationale**: the seams are the only place the rules can be wrong in ways the agents could not
see (each agent saw a seam only from its own side). The reviewer sees both sides at close
zoom, at a fraction of the cost of a whole-map review, and reads crops at the zoom that
chunking was for.

**Alternatives considered**: review the whole map (coarse zoom, the original problem); let the
reviewer return edits (move/delete by id) instead of the strips' complete content: harder for a
model to get right than "draw what should be here", and harder to validate.

## R7. Running agents at the same time

**Decision**: `llm/orchestrator.py` runs the chunk agents on a `ThreadPoolExecutor` with
`max_parallel` workers (default 4) sharing one Anthropic client (the SDK's sync client is safe
to share across threads). One pass deadline for all. Before a chunk starts, the orchestrator
checks the deadline and the summed live cost against the choice's `max_cost_usd`; if either is
used up, the chunk is `skipped`. The review runs after all agents, on the calling thread. Every
state change is reported through an `on_update` callback (the app's progress view; the batch
tool ignores it).

**Risk**: four requests at once are likelier to hit a rate limit. The app sends with
`max_retries=0`; a 429 fails that chunk (`rate_limit`) and the others continue. Lower
`max_parallel` if it happens.

**Alternatives considered**: `asyncio` (the tool loop is synchronous and tested; nothing gained
at four agents); one after another (four times the wait; loses the demo).

## R8. Orchestrator: code plus one model step

**Decision**: the orchestrator is Python (layout, dispatch, limits, rule merge) plus one model
step it calls, the seam review. The pattern is orchestrator-workers: N independent agents with
their own context, tools and limits, a deterministic merge, and an orchestrator agent that
checks the joins. This is what the owner presents.

## R9. Partial failure

**Decision**: each chunk ends `done` (answer kept, including "kept last submission" after an
error), `failed` (a `FailureKind` from `app.tracer.classify`), or `skipped`. The pass:

- at least one chunk `done`: a `TraceResult` with the merged (and, if it ran, reviewed) mask,
  the per-chunk reports and the untraced cores. Seams next to an untraced chunk are still
  reviewed (the reviewer sees what is there). The message says how many parts were not traced
  and why, that the file covers the rest, and that running again retries the whole map.
- no chunk `done`: a `PassFailure` with the first failed chunk's kind, or `pass_limit` if all
  were skipped. No review runs.

The missing-key check runs once, before any chunk. Each failure kind is tested for a chunk and
for the review (FR-012).

**Alternatives considered**: retry only the failed chunks (needs the earlier answers kept in the
session and a second merge path; out of scope).

## R10. Batch tool

**Decision**: `python -m llm.run --chunked [--agents haiku|sonnet|opus]` on the usual jobs,
scored the usual way (`score_row`, 32 px per square, true map size). It scores **both** the
rule-merged answer and the reviewed one from the same run (FR-014), as `merged_*` and plain
columns. Folders per map: `merged.json`, `answer.json` (final), `.dd2vtt`, `preview.jpg`,
`trace.json` (totals), `merge.json`, `review/` (trace, responses, views, submission) and
`chunks/<i>/`. The cost prompt states chunks x per-chunk cost + review, per map and in total.

## R11. Showing the orchestration in the app

**Decision**:

- **Selector**: a `gr.Radio` (Haiku / Sonnet / Opus, default Sonnet) next to the chunked button;
  the button label (chunk count, expected time and cost) follows the selector and the map size.
- **While running**: the preview shows each chunk's core outlined, lightly filled by state
  (waiting grey, tracing blue, done green, failed red, skipped grey with a cross) and numbered;
  when the review runs, the strips are drawn in amber. The progress line: "Working… 12 s ·
  2 of 4 parts done" then "· checking the borders". The state lives in a thread-safe
  `ChunkBoard`, polled each second as the page already does.
- **After**: the normal preview with untraced parts outlined, and a `gr.Dataframe` under it with
  one row per agent (part, state and reason, time, cost, closer views, walls, portals, lights in
  its own answer) and a last row for the review (model, time, cost, lines changed or "not
  run"). Hidden for the other passes and cleared by a new upload or another pass (FR-019).

## R12. Haiku and the constitution

Constitution 2.1.0 (commit `faddcb2`) allows the third model only in the chunked pass, with
estimates marked until measured. `Settings.profiles` stays `quick` and `deep`; Haiku appears
only under `[chunked.agents]`.

## R13. The paid evaluation

The full US3 run over the three choices on four maps is about $0.52 (Haiku, 16 parts per map
since 23.11) + $1.16 (Sonnet) + $3.80 (Opus) ≈ **$5.50**. Plan: Sonnet first (≈ $1.2, the default and the demo), then Haiku
(≈ $0.5), then Opus only if the owner wants the row for the slides. Each is a separate run the
owner approves, with its estimate printed before any call.
