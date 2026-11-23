# Quickstart: Validating Chunked Map Tracing

Steps 1-3 are free. Steps 4 and 5 make paid calls and are the **project owner's** to run and
approve (constitution II).

## Prerequisites

- On branch `002-chunked-map-tracing`; the image builds: `docker compose build`.
- `.env` holds `ANTHROPIC_API_KEY` (steps 4 and 5 only).
- Reference maps in `data/reference/` (committed).

## 1. Tests and lint (no paid calls)

```
docker compose run --rm app pytest
docker compose run --rm app ruff check . && docker compose run --rm app ruff format --check .
```

Expected: all pass. New tests, all with the fake client (`tests/conftest.py`) or none:

- **layout**: cores partition the map for 1 x 1, 13 x 13, 25 x 25, 27 x 14, 50 x 50 and
  200 x 200; never more than 4 per side; windows hold their cores ([data-model.md](data-model.md));
- **merge and review apply**: the guarantees in [contracts/orchestrator.md](contracts/orchestrator.md);
- **tracer**: `trace_map(window=None)` sends the same first request as before; with a window,
  the overview is outlined and crops stay inside the window;
- **review**: strips and crops for a 2 x 2 and a 3 x 2 layout; a scripted reviewer that
  submits is applied; refusal, limit, timeout and API errors keep the merged answer;
- **orchestrator**: four scripted agents plus a reviewer give one final answer; deadline and
  cost limits skip the chunks not started and the review; one failed chunk leaves the others;
  every failure kind ends its chunk;
- **config**: all three agent choices load; missing price, unknown orchestrator, or more than 4
  per side fails; expected figures follow map size, choice and the detect option;
- **app**: labels follow the selector and the map size; a partial result shows the partial
  message and outlines; an unreviewed result shows the seams notice; no chunk done gives the
  right `PassFailure`; the board passes through its states; the agent table has one row per
  chunk plus the borders row, and is `None` after a single-session pass
  ([contracts/app.md](contracts/app.md)).

## 2. The merge loses nothing (no paid calls)

A test cuts the demo map's own `.dd2vtt` (walls, portals, lights) into the windows of a 2 x 2
layout, as if four perfect agents had answered, merges them, and scores the result against the
original with `eval.metrics`. Expected: wall boundary F1 >= 0.99 and portal recall 1.0 (SC-003).
The same test applies an empty review submission and checks that only the strips lost their
content.

## 3. The whole pass with the fake client (no paid calls)

A service test runs `service.begin_pass(chunked)`, `tracer.run_pass(..., client=<routing fake>)`,
`service.finish_pass`, then `service.export`: the exported file loads with
`data.rasterize.load_uvtt` and has the final counts; `agent_table` has 5 rows for a 2 x 2 map.

## 4. One live chunked pass in the app (paid, about $0.29 with Sonnet; owner)

```
docker compose run --rm --service-ports app python -m app.main
```

Upload the castle reference map's image, keep 25 x 25, keep "Sonnet 5.5", click the chunked
pass. Expected:

- the button shows 4 agents, about 45 s and about $0.29, marked as an estimate;
- while it runs, the preview shows four numbered parts going waiting → tracing → done, then the
  two border strips in amber while the orchestrator checks them;
- the status line names the agents, the orchestrator, time and cost; the table shows 4 agent
  rows and the borders row;
- "Accept mask" downloads one `.dd2vtt`. Import it into Roll20 (Page Menu → Upload Background)
  and check the walls at x = 12.5 and y = 12.5 have no gaps (owner; US1 scenario 5).

Optionally repeat with Haiku (about $0.07).

## 5. Reference evaluation (paid; owner approves each run first)

```
docker compose run --rm app python -m llm.run --reference --chunked --agents sonnet --run <date>_chunked_sonnet
docker compose run --rm app python -m llm.run --reference --chunked --agents haiku  --run <date>_chunked_haiku
docker compose run --rm app python -m llm.run --reference --chunked --agents opus   --run <date>_chunked_opus
```

About $1.2, $0.3 and $3.8 (research.md R13); each prints its estimate and asks before sending
anything. Record in `docs/results.md` a new section: the table (same columns as the 13.11
reference evaluation, plus agents, chunks, review state, and the rule-merged scores next to the
reviewed ones), run names, costs and sample size (one run per map), and the comparison with
the 13.11 single-session rows against SC-001, SC-002, SC-005 and SC-009. Then set each measured
choice's expected figures in the config and `estimate = false`.
