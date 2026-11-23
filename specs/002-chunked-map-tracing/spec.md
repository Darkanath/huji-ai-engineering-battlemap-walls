# Feature Specification: Chunked Map Tracing

**Feature Branch**: `002-chunked-map-tracing`

**Created**: 2026-11-23

**Status**: Draft

**Input**: User description: "When providing the battlemap to the LLM, it is best to chunk the map to smaller chunks, that will cater to the context and memory. I'd like to chunk a map and provision it to multiple agents, via an orchestrator that each agent will work on a small chunk, return their results and at the end, the orchestrator will merge the results into a single .uvtt file"

## Context

Today one model session traces a whole map. It gets the whole map at one zoom level, then its
four quarters at a higher one, and it can ask for closer crops. Every image sent to the model is
capped at the same longest side, so the larger the map, the fewer pixels each square gets. On a
large map, each square gets few pixels in the quarters too. The session's conversation also
grows with every crop and every answer it checks against the map, until a turn, view or cost
limit stops it. Measurements so far (`docs/results.md`) cover maps of about 25 x 25 squares and
show the fast pass weakest on caves and doors: on 13.11 it found no doors at all on the tavern
and the castle, and it asked for no closer views on any map. On those maps (25 x 25 squares at
70 px per square) the quarter views already show every pixel the image has, so on maps of
that size chunking adds focus, not detail: each agent has a small area and its own budget of
closer views. On larger maps it also adds detail.

This feature splits a map into overlapping chunks and gives each chunk to its own tracing
agent, which sees only its chunk (plus enough of the surroundings to understand it). An
orchestrator then merges the agents' answers by fixed rules, an orchestrator model reviews the
borders between chunks at close zoom and fixes them, and the result is one Universal VTT file.
Each agent attends to a small area with its own budget of closer views, no single session has
to hold the entire map, and on maps larger than the 25 x 25 reference maps each chunk is also
shown at a closer zoom than the single session's quarter views.

The chunked pass is a third pass in the app, next to "Suggest walls" and "Deeper examination",
and is part of the final presentation: it shows a multi-agent orchestration (one orchestrator,
several tracing agents working at the same time, one merged result) working on a real task.

## Clarifications

### Session 2026-11-23

- Q: When is a map chunked? → A: Always, whenever the chunked pass is chosen; a map smaller
  than one chunk is simply one chunk. A size threshold may be added later from measurements.
- Q: How are chunk answers merged? → A: By fixed geometric rules only (join walls at borders,
  drop duplicates within a set distance; planning implements the duplicate rule by ownership,
  research.md R4); no model call in the merge. A model review step may
  be added later if seam errors show up in the scores. (Extended by the model question below:
  the merge itself stays rule-based, and a seam review by an orchestrator model follows it.)
- Q: Where does chunked tracing live? → A: In the app as a third pass next to the two existing
  ones, and in the batch tool for scoring. It is part of the demo of multi-agent orchestration.
- Q: What should the chunked pass do on a large map that would need many chunks? → A: Cap at
  16 chunks (at most 4 across and 4 down); larger maps get larger chunks instead of more of
  them, so one click costs at most about 16 agents.
- Q: When a chunked pass finishes, what should the page show about the individual agents? →
  A: The totals in the status line, plus a table under the preview with one row per agent.
- Q: Which model should the chunked pass's agents use in the app? → A: The user picks Haiku,
  Sonnet or Opus for the agents with a selector next to the chunked button. An orchestrator
  model (Sonnet for Haiku or Sonnet agents, Opus for Opus agents) then reviews the borders
  between parts: after the rule-based merge, it gets close-up crops along each border with the
  merged lines drawn, and fixes what crosses the borders.

### Session 2026-11-23 (after the first live runs, T037)

- Q: Should every model get the same part size? → A: No: each model has its own part size in
  configuration. Haiku needs smaller parts (about 7 squares: 16 parts on a 25 x 25 map);
  Sonnet and Opus keep about 13 (4 parts). Each part still gets its own fresh agent session,
  at most 4 running at once; the other parts wait for a free agent. The 16-part cap stays.
- Q: Haiku's 16 parts at 4 agents at a time take about 140 s, over SC-004's "twice the single
  session" (about 70 s for Haiku). Amend the criterion or run more Haiku agents at once? → A:
  Amend SC-004: the bound applies to Sonnet and Opus agents; Haiku is the cheap choice, not the
  fast one, and gets its own bound of 3 minutes on a 25 x 25 map.

## User Scenarios & Testing *(mandatory)*

### User Story 1 - Trace a map in chunks and get one file (Priority: P1)

The project owner runs a chunked trace on a map. The map is split into overlapping chunks, each
chunk is traced by its own agent, and the results are merged into a single .uvtt file with walls,
portals and lights. The file imports into Roll20 like the file from a single-session pass, with
no doubled walls, broken joins or duplicate doors and lights where chunks meet.

**Why this priority**: it is the whole feature. Without a merged file, there is nothing to
measure or use.

**Independent Test**: run a chunked trace with the fake model client on the demo map, where
each fake chunk agent returns walls that cross into its neighbours' overlap. Check that the
output is one valid Universal VTT file, that walls crossing a chunk border are continuous, and
that a portal or light inside an overlap appears once.

**Acceptance Scenarios**:

1. **Given** a 25 x 25 square map and a chunk layout of 2 x 2, **When** a chunked trace runs,
   **Then** four chunk agents run, each sees only its chunk and its overlap at a closer zoom
   than the single-session overview, and one .uvtt file comes out.
2. **Given** a wall that runs straight across a border between two chunks, **When** the results
   are merged, **Then** the file has one continuous wall there, with no gap and no second copy
   running alongside it.
3. **Given** a door or a light that falls inside the overlap of two chunks, and both agents
   report it, **When** the results are merged, **Then** the file has it once.
4. **Given** a merged answer for a map with more than one chunk, **When** the seam review runs,
   **Then** the orchestrator model sees close-up crops along every border between chunks with
   the merged lines drawn on them, and its corrections replace the merged lines only within a
   set distance of the borders; everything else stays as the agents traced it.
5. **Given** a merged file, **When** it is uploaded to Roll20, **Then** dynamic lighting works
   with it the way it works with a single-session file (checked by the project owner).

---

### User Story 2 - Use chunked tracing from the app (Priority: P2)

A user of the app can choose a chunked pass for a map, as a third button next to "Suggest
walls" and "Deeper examination", and picks the agents' model (Haiku, Sonnet or Opus) with a
selector next to it. Before the click, they see its expected
time and cost, which grow with the number of chunks. While it runs, they see how many chunks are
done. After it finishes, they see the actual time and estimated cost, and the same preview and
download as with any other pass. They can see the orchestration happen: the chunk layout drawn
over the map, and each chunk's state (waiting, tracing, done, failed) as the agents work.

**Why this priority**: it is what the project owner presents. The orchestration must be visible
and work in the app, not only in a batch tool. It comes after User Story 1 because it needs
the merged result.

**Independent Test**: call the app's service functions with the fake client for a chunked pass.
Check the cost and time shown before and after, the progress messages, and that the exported
file matches the merged answer.

**Acceptance Scenarios**:

1. **Given** an uploaded map, its size in squares and a model chosen in the selector, **When**
   the user looks at the chunked pass's button, **Then** it shows the number of chunks, the
   expected time and the expected cost for this map with that model, including the seam
   review; changing the selector or the map size updates them.
2. **Given** a chunked pass running, **When** chunks start and finish, **Then** the user sees
   the chunk layout over the map and each chunk's state, and how many are done out of the
   total.
3. **Given** a finished chunked pass, **When** the user downloads the result, **Then** they get
   one .uvtt (or .dd2vtt) file, as with any other pass.
4. **Given** the two existing passes, **When** the chunked pass is added, **Then** they behave
   exactly as before.
5. **Given** a finished chunked pass, **When** the user looks under the preview, **Then** they
   see one row per agent with its part number, final state (and the reason, if it failed or was
   skipped), time, estimated cost, closer views asked for, and the walls, doors and windows,
   and lights in its own answer before merging.

---

### User Story 3 - Measure chunked tracing against the single session (Priority: P3)

The project owner runs the chunked trace on the labeled reference maps and scores it the same
way as the existing profiles (wall boundary F1, pixel IoU, portal recall), with time and cost
per map. The results go into `docs/results.md` next to the single-session rows, so it is clear
whether chunking is better, worse or the same, and at what price.

**Why this priority**: the project only calls a change an improvement once it has been scored
(constitution III). Whether chunking is worth more calls is unknown until it is measured. The
app pass (User Story 2) can ship before this, with expected time and cost worked out from
per-chunk estimates in configuration; this story replaces them with measured figures and
decides what the presentation can claim about accuracy.

**Independent Test**: run the scoring on the reference maps with the fake client (no paid
call). A scores table must come out, with the chunked method as its own row and its time and
cost columns filled in.

**Acceptance Scenarios**:

1. **Given** the reference maps, **When** the owner runs the batch tool with chunking on,
   **Then** each map gets a score in the same format as single-session runs, plus its chunk
   count, time and estimated cost.
2. **Given** a planned paid evaluation, **When** it is about to start, **Then** its estimated
   cost (chunks times cost per chunk, plus the seam review, times maps) is shown first, and it runs only after the
   owner approves it.

### Edge Cases

- **Map small enough for one chunk.** The map is traced as one chunk, with no merging, and the
  result matches a single-session trace's format.
- **A map whose size is not a multiple of the chunk size.** The chunks still cover every square.
  Each side is split into equal slices (a 27-square side becomes three slices of 9, not
  13 + 13 + 1), so no chunk is a thin strip; every core is at least 2 squares across.
- **A chunk agent fails** (refusal, timeout, limit, unreadable answer). The other chunks' results
  are kept. The user is told in plain language which part of the map has no tracing, and the
  file is still produced for the rest, with that area marked as untraced in the run log. The
  user can retry the pass.
- **Every chunk fails** (for example, missing key or no network). The user gets one
  plain-language message, the same as for a failed single-session pass, and no file.
- **The cost limit for the whole map is reached partway.** Chunks not yet started are not run.
  The user is told which part of the map is untraced and what it cost so far.
- **Two agents disagree in an overlap** (for example, one draws a wall and the other a door at
  the same place, or their walls are a fraction of a square apart). The merge applies one fixed
  rule (see FR-008), so the same inputs always give the same file.
- **A chunk with nothing in it** (open ground, water). Its agent returns an empty answer, which
  is valid and merges as nothing.
- **A wall that ends exactly on a chunk border.** It must not be extended or cut off by the
  merge.
- **A round room or arc that spans chunks.** It comes out as a connected shape, not as two arcs
  with a gap or an overlap between them.
- **The seam review fails or hits a limit.** The rule-merged answer is kept and exported, and
  the message says the borders between parts were not checked.
- **The seam review moves a line out of its strip.** Only the parts of its corrections inside the
  border strips are used; it cannot change the rest of the map.
- **A very large map** (for example 200 x 200 squares). It still gets at most 4 x 4 chunks, each
  about 50 squares across, so the pass's cost stays bounded and every part of the map is traced;
  each chunk is then shown at less than the image's own detail if the view size cap requires it.
- **Map size detection.** The size is worked out once for the whole map, before chunking, as in
  the single-session pass. Chunks are laid out in grid squares, from that size.
- **Detection changes the chunk count.** The size in the fields gives 4 parts, but detection
  finds a larger map that needs 16. The button showed, before the click, both the figures for
  the size in the fields and the most the pass can cost (16 parts), so the larger bill was
  visible; the choice's cost limit still applies.

## Requirements *(mandatory)*

### Functional Requirements

- **FR-001**: The system MUST split a map into a grid of rectangular chunks laid out in grid
  squares. Together the chunks cover every square of the map, and each chunk overlaps its
  neighbours by a set number of squares.
- **FR-002**: Chunk size and overlap MUST come from configuration, not code, so they can be
  tuned without code changes. Each chunk's first view MUST show its squares at no less than
  the image's own pixels per square (or the view size cap, if that is lower), so chunking never
  shows a square at less detail than the image has. (Corrected 2026-11-23 during planning: on
  the 25 x 25 reference maps the quarter views already exceed the image's own resolution, so
  "more pixels than the quarters" could not be met by any chunk size.)
- **FR-003**: When the chunked pass is chosen, the map MUST always be split by the chosen
  agents' model's configured part size and the overlap; a map no larger than one chunk becomes a single chunk. The user does
  not choose the chunk grid. A map has at most 4 chunks across and 4 down (16 in all; the
  limit is in configuration): when the configured chunk size would need more, the chunks grow
  instead, so the whole map is always covered.
- **FR-004**: Each chunk MUST be traced by its own agent session. The agent sees its chunk at a
  closer zoom, with grid labels in whole-map coordinates, plus a small overview of the whole map
  with its chunk outlined, so it understands where it is. It can ask for closer crops inside its
  chunk and check its answer drawn over its chunk, like the single-session tracer.
- **FR-005**: Chunk agents MUST report walls, portals and lights in whole-map grid squares, using
  the same answer format as the single-session tracer, so merging needs no coordinate
  translation of its own and the existing export is reused.
- **FR-006**: Each chunk agent MUST be told which part of its view is the overlap, and to trace
  through the overlap to its outer edge, so that every border is covered by two agents.
- **FR-007**: The orchestrator MUST run the chunk agents, collect their answers, merge them
  into one answer for the whole map (FR-008), have the seams reviewed (FR-020), and export the
  result as one Universal VTT file at
  70 px per square, the same way as a single-session result.
- **FR-008**: The merge MUST use fixed geometric rules only, with no model call, and its
  distances (in squares) MUST come from configuration. It MUST: join walls that meet across a
  border into continuous walls; keep one copy of a wall, portal or light that two agents
  report in an overlap; keep the wall cut at a portal; and give the same output for the same
  inputs.
- **FR-009**: Chunk agents MUST be able to run at the same time, up to a limit set in
  configuration, so a chunked pass does not take the sum of all chunk times.
- **FR-010**: The whole chunked pass MUST obey limits for the whole map (total cost and a
  deadline), set in configuration, in addition to the per-chunk limits. Reaching one stops new
  chunks from starting and is reported to the user.
- **FR-011**: Before a chunked pass starts, the system MUST show its expected time and cost for
  this map (formula in FR-018). When "Detect map size" is on, the chunk count can change during
  the pass, so the button MUST also show the most the pass can cost and take (the 4 x 4
  layout's figures with the chosen model). After the pass, the system MUST show the actual
  time and estimated cost, summed over all chunks, the seam review and the map-size step.
- **FR-012**: A failure in any chunk MUST reach the user as a plain-language message naming the
  parts of the map affected by number (e.g. "part 3 of 4"), matching the numbers in the preview
  and the agent table; it MUST NOT crash the pass or show a stack trace. Each failure type
  (refusal, limit, missing key, network, timeout, unreadable answer) MUST have a test, for a
  chunk agent and for the seam review.
- **FR-013**: The run log for a chunked pass MUST record the agents' and the orchestrator's
  models, and, per chunk: its window in squares, the
  model, turns, views, submissions, time, estimated cost and how it ended. It MUST also record
  the merge result (items joined and items dropped as duplicates) and the seam review (turns,
  views, cost, time, lines changed, how it ended).
- **FR-014**: The batch evaluation tool MUST be able to run the chunked method on the reference
  maps and score it with the existing metrics at 32 px per square, so it can be compared row by
  row with single-session runs in `docs/results.md`, with the agents' model chosen as in the app.
  It MUST score both the rule-merged answer and the reviewed answer of the same run, so the seam
  review's effect is measured without paying twice.
- **FR-015**: Tests MUST cover chunk layout, the merge rules and the orchestrator with the fake
  model client; no test makes a paid call.
- **FR-016**: The single-session passes ("Suggest walls" and "Deeper examination") MUST keep
  working unchanged. The chunked pass is added to the app as a third pass next to them, with its
  own button, expected time and cost, and the same validation, privacy notice, preview and
  download as the other passes.
- **FR-017**: While a chunked pass runs, the app MUST show the chunk layout over the map and
  each chunk's state (waiting, tracing, done, failed, skipped), updated as agents start and
  finish, and show when the orchestrator model is reviewing the seams.
- **FR-018**: A selector next to the chunked button MUST offer Haiku, Sonnet and Opus for the
  agents (default Sonnet). The orchestrator model MUST follow from it: Sonnet for Haiku or
  Sonnet agents, Opus for Opus agents. Model names, effort and the pairing live in
  configuration. The button's expected time and cost MUST come from configuration (per-chunk
  figures for the chosen model times the chunk count for this map, plus the seam review and
  the map-size step when it is on) and be updated after the measured run of User Story 3.
- **FR-019**: After a chunked pass, the app MUST show a table with one row per agent: part
  number, final state, the plain-language reason for a failed or skipped part, time, estimated
  cost, closer views asked for, and the counts of walls, portals and lights in that agent's own
  answer before merging. The table is cleared when a new image is uploaded or another pass
  replaces the result, and is not shown for the single-session passes. A last row shows the
  seam review: its model, time, cost and how many lines it changed.
- **FR-020**: When a map has more than one chunk, the orchestrator model MUST review the merged
  answer along every border between chunks: it gets close-up crops of each border strip (a set
  width in squares, from configuration) with the merged lines drawn on them, may ask for closer
  crops within those strips, and submits corrected lines for the strips. Its corrections
  replace the merged walls, portals and lights only inside the strips; nothing outside them
  changes. Its time and cost count toward the pass's figures and limits. If the review fails
  or runs out of time or budget, the rule-merged answer is kept, and the user is told the seams
  were not reviewed. A one-chunk map has no seams and no review.

### Key Entities

- **Chunk**: a rectangular window of the map in grid squares (its core area plus its overlap
  margin), its position in the chunk grid, and its neighbours.
- **Chunk layout**: the chunks for one map, worked out from the map size, chunk size and
  overlap.
- **Chunk answer**: one agent's walls, portals and lights in whole-map squares, plus its run
  record (time, cost, turns, how it ended).
- **Merged answer**: the single answer for the whole map produced from all chunk answers, in the
  same form as a single-session answer, so the existing export and preview apply.
- **Seam**: a border between two neighbouring chunks' areas, and the strip of set width along
  it that the seam review may change.
- **Seam review**: the orchestrator model's check of every seam: its model, the strips it saw,
  the lines it changed, time, cost and how it ended.
- **Chunked run record**: the per-chunk records, the merge summary, the seam review, and totals for time and
  cost.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: On the reference maps, the chunked method's wall boundary F1 is at least as high
  as the single-session pass with the same model, on every map; on the mine (`dd06_a`, the cave map)
  with the fast model it is higher than today's 0.545 (13.11 reference run).
- **SC-002**: Portal recall of the chunked method on the reference maps is at least as high as
  the single-session pass with the same model; with the fast model it is above 0 on the tavern
  (`dd04_a`) and the castle (`dd07_a`), where the single session found none on 13.11.
- **SC-003**: In merged files, no wall that crosses a chunk border has a gap at the border
  larger than the scoring tolerance (0.1 square), and no portal or light is counted twice;
  checked on every reference map.
- **SC-004**: A chunked pass on a 25 x 25 map with Sonnet or Opus agents finishes in no more
  than twice the single-session time with the same model, with chunks running at the same
  time. With Haiku agents (smaller parts, so 16 parts at 4 at a time) it finishes in no more
  than 3 minutes. (Amended 2026-11-23, see Clarifications.)
- **SC-005**: The estimated cost shown before a chunked pass is within 50% of the actual
  estimated cost after it, on the reference maps.
- **SC-006**: Every chunk and seam-review failure case in FR-012 and FR-020 produces a plain-language message and, where
  any chunk succeeded, a file; verified by tests.
- **SC-007**: In the app, a chunked pass on a reference map shows the chunk layout and every
  chunk's state change, and ends with a downloadable file, in a live run the owner can present.
- **SC-008**: The results, with cost and sample size, are recorded in `docs/results.md`, and the
  owner can say from them whether chunking is worth its price, and for which maps.
- **SC-009**: On every reference map, the seam review does not lower wall boundary F1 or portal
  recall compared with the rule-merged answer of the same run.

## Assumptions

- The agents' model is chosen per pass (Haiku, Sonnet or Opus, default Sonnet); every agent in
  a pass uses the same one. Haiku was weak on caves on 13.11 (`docs/results.md`); it is offered
  because it is about a twentieth of Sonnet's price, and its chunked scores are measured like
  the others.
- Offering Haiku in the app adds a third model choice, while the constitution's Domain section
  names two profiles (fast Sonnet, deep Opus). This needs a constitution amendment (MINOR, to
  2.1.0) approved by the project owner before it is built, with `CLAUDE.md` updated in the
  same change.
- The map size is known before chunking: typed by the user or worked out by the existing
  map-size step, once per map, not per chunk.
- Part sizes per model, with a 1-square overlap: Haiku about 7 squares (16 parts on the
  default 25 x 25 map), Sonnet and Opus about 13 (4 parts). They are tuned from measurements.
- A chunked pass costs more than a single-session pass (several sessions, each with its own
  images and conversation). The goal is better accuracy on caves, doors and large maps, not a
  lower price. Expected time and cost are in configuration as estimates, shown as such, until
  the first measured run replaces them.
- The paid evaluation of the chunked method on the reference maps is a run the owner approves,
  with its estimated cost stated first.
- The existing single-session tracer, views, export and metrics are reused. Chunking adds a
  layer around them rather than replacing them.
- No new external dependency is expected. Joining and deduplicating geometry can be done with
  the packages already installed. If a geometry library turns out to be needed, the already
  agreed `shapely` is considered first, with the owner's approval.
- Only the owner's own reference maps are scored. Third-party maps are used only to try the
  feature.
