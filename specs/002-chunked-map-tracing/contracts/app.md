# Contract: App (service, tracer, page)

Extends `specs/001-battlemap-tracer-app/contracts/service.md` and `ui.md`; everything there
still holds for "Suggest walls" and "Deeper examination".

## `app/tracer.py`

`run_pass(image, map_size, fallback_size, kind, settings, client=None, size_source=...,
agents: AgentChoice | None = None, board: ChunkBoard | None = None) -> TraceResult | PassFailure`

- `kind == PassKind.chunked`: the same key check and map-size step as today (once, on the
  `[size_step]` profile); the board is rebuilt if the size changed; then
  `llm.orchestrator.trace_chunks` with the choice's `deadline_s`, its callback updating `board`.
- At least one chunk `done`: `TraceResult` with the final mask, `agents`,
  `orchestrator_model`, `chunks` (failure kinds from `classify`), `review` and `untraced`.
- No chunk `done`: `PassFailure` with the first failed chunk's kind, or `pass_limit` if all
  were skipped.
- Never raises. Logs `chunk_finished` per chunk (part, window in squares, model, state,
  failure, turns, views, submissions, cost, seconds; FR-013), `review_finished` (state, model, turns,
  views, cost, seconds, removed, added), and `pass_finished` / `pass_failed` with `agents`,
  `orchestrator`, `chunks`, `chunks_failed`, `chunks_skipped`, `review` and the merge counts.

## `app/service.py`

| Function | Change |
| --- | --- |
| `set_agents(session, choice)` (new) | sets the selector's value; anything else is ignored |
| `can_start(session, kind)` | `chunked` behaves like `quick`: an image and nothing running |
| `begin_pass(session, kind)` | for `chunked`, a `PassTicket` carrying `agents`, and `session.board` set for the layout of the size used (rebuilt by the tracer if the size step changes it) |
| `finish_pass(...)` | clears `session.board`; otherwise unchanged |
| `button_labels(settings, map_size, detect, agents)` | new signature; the existing callers (`app/main.py`) and tests are updated, and the two existing labels are unchanged. Adds `PassKind.chunked`: e.g. `"Chunked pass: 4 Sonnet agents (about 45 s, about $0.29, estimate)"`, from `ChunkedSettings.expected`; "estimate" while the choice's `estimate` is true. With `detect` on it adds the upper bound from `ChunkedSettings.expected_max`: `"… for 25 x 25; up to $1.04 and 128 s if the detected size needs 16 parts"` (FR-011) |
| `preview(session)` | while a chunked pass runs: the map with the board drawn (`render.chunk_overlay`); after: the mask, with untraced parts outlined |
| `progress_line(session)` (new) | `"Working… 12 s"`; for a chunked pass `" · 2 of 4 parts done"`, then `" · checking the borders"` |
| `agent_table(session)` (new) | rows for the last result if it is chunked, else `None`: `Part`, `State`, `Time`, `Cost`, `Closer views`, `Walls`, `Doors/windows`, `Lights`, then a row `Borders (Sonnet 5.5)` with state, time, cost and "n lines changed" or the reason it did not run |
| `status_line(session)` | chunked: `"Chunked · 4 Sonnet 5.5 agents + Sonnet 5.5 orchestrator · 41 s · about $0.27 · 14 walls, …"` |
| `result_message(session)` | chunked with `untraced` and/or review not `done`: `errors.partial_message(...)` and/or `errors.SEAMS_NOT_CHECKED`; otherwise unchanged |

## `app/errors.py`

- `partial_message(parts: list[int], total: int, kind: FailureKind | None) -> str` (`parts` are
  the 1-based part numbers shown in the preview and the table), e.g. "Part 3 of 4 could not be
  traced (the model service was busy)." or "Parts 2 and 4 of 4 could not be traced (…). The file has everything
  else; that part is outlined in the preview. Run the chunked pass again to retry the whole
  map." `kind=None` (skipped) reads "the pass reached its time or cost limit".
- `SEAMS_NOT_CHECKED = "The borders between the parts were not checked, so walls may be broken
  or doubled where the parts meet."`
- A short plain reason per `FailureKind` for the table's State column ("refused", "timed out",
  "service busy", …).

## `app/render.py`

`chunk_overlay(image, snapshot, map_size) -> Image`: each core outlined, lightly filled by state
(waiting grey, tracing blue, done green, failed red, skipped grey with a cross) and numbered;
seam strips in amber while the review runs. `overlay(...)` also outlines `result.untraced` in
grey.

## Page (`app/main.py`)

- Under "Deeper examination": a radio "Agents' model" (Haiku 5.5 / Sonnet 5.5 / Opus 5.5,
  default Sonnet) and the chunked button, enabled with the same rules as "Suggest walls", its
  label from `button_labels`; changing the radio or the map size updates the label.
- One line under it: "Splits the map into parts and traces each with its own AI agent at the
  same time; an orchestrator model then checks the borders where the parts meet."
- While it runs: every button and the radio locked; each one-second tick updates the preview
  (board) and the progress line; the other passes' ticks are unchanged.
- After it: a table under the preview (`gr.Dataframe`, read-only) from `agent_table`; hidden
  when that returns `None`.
- Notice, upload checks, map-size fields, detect option, file type and "Accept mask" apply to
  the chunked pass unchanged.
