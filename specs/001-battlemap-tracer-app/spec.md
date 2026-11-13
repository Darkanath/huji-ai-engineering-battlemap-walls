# Feature Specification: Battlemap Tracer App

**Feature Branch**: `001-battlemap-tracer-app`

**Created**: 2026-11-13

**Status**: Draft

**Input**: User description: "Build a battlemap tracer web app for tabletop game masters. The user uploads a top-down battlemap image and gets back a Universal VTT file with walls, portals and light sources already placed, ready to import into Roll20 for dynamic lighting and fog of war." (Full description given with the command: inputs, user flow, what gets detected, failure handling, out of scope and success criteria. All of it is carried into the sections below. Amended 2026-11-13: automatic grid detection, out of scope in the description, is now in scope, done by the vision model as part of a pass.)

## Overview

A game master has a finished battlemap image and wants dynamic lighting and fog of war in
Roll20. Placing walls, doors and lights by hand takes a long time per map. This app does the
placing: the user uploads the image, the app suggests a mask (walls, portals and lights drawn
over the map), and the user downloads it as a Universal VTT file that Roll20 imports directly.

It is a single-user tool that the operator runs on their own machine. The operator sets the
AI provider key in configuration; the person using the app never enters a key. Every analysis
sends the uploaded image to a third-party vision-model provider and costs money, so the app
tells the user both things before they click.

Two passes are offered because they differ in price and quality. The fast pass is cheap and
good on ordinary buildings. The deep pass costs about four times as much and takes about
three times as long, and it fixes most of what the fast pass misses: cave outlines, and doors
in castles and other complex structures.

## User Scenarios & Testing *(mandatory)*

### User Story 1 - Fast suggestion to a downloadable file (Priority: P1)

A game master uploads a map image, confirms or corrects the map size in grid squares, and clicks
"Suggest walls". After a short wait the suggested walls, portals and lights appear drawn over
the map. They click "Accept mask" and download a Universal VTT file that they upload to Roll20.

**Why this priority**: This is the whole product in its smallest form. With only this story
built, a user already gets a working file for a simple building map.

**Independent Test**: Upload the reference building map with its map size, click "Suggest
walls", click "Accept mask", import the downloaded file into Roll20 and check that fog of war
follows the walls.

**Acceptance Scenarios**:

1. **Given** the app is open with no image, **When** the user looks at the map size fields,
   **Then** they show 25 x 25, the "detect map size from the image" option is on, and
   "Accept mask" is visible but disabled.
2. **Given** a valid image is uploaded, **When** the user looks at the "Suggest walls" button,
   **Then** it shows its expected time and cost (from the config; about 25 s, about $0.10 as
   measured on 13.11) before any click.
3. **Given** a valid image and map size, **When** the user clicks "Suggest walls" and the pass
   succeeds, **Then** the map is shown with walls, portals and lights drawn over it, each kind
   visually distinct from the other two.
4. **Given** a pass has just succeeded, **When** the user reads the status line, **Then** it
   shows the model used, the time taken, the estimated cost and the model's own note on what
   it was unsure of.
5. **Given** a mask is on screen, **When** the user picks `.dd2vtt` and clicks "Accept mask",
   **Then** a file with that extension is downloaded containing the walls, portals and lights
   on screen and the map image embedded at 70 px per grid square.
6. **Given** a mask is on screen, **When** the user picks `.uvtt` and clicks "Accept mask",
   **Then** the downloaded file has the `.uvtt` extension and the same content.
7. **Given** a mask and status from an earlier map are on screen, **When** the user uploads a
   new image, **Then** the previous image, mask and status are cleared and "Accept mask" is
   disabled again.

---

### User Story 2 - Deeper examination of a hard map (Priority: P2)

The fast suggestion on a cave or castle map misses cave outlines or doors. The user reads the
note next to "Deeper examination", decides the deep pass is worth its price, and clicks it.
The map is traced again from scratch and the new mask replaces the old one.

**Why this priority**: The fast pass alone is not good enough on caves and complex structures.
The deep pass is what makes the app useful on those maps, but it builds on the screen and flow
of Story 1.

**Independent Test**: Upload the reference cave map, run "Suggest walls", then "Deeper
examination", and compare the two masks against the map's labels.

**Acceptance Scenarios**:

1. **Given** no suggestion exists yet, **When** the user looks at "Deeper examination",
   **Then** it is disabled.
2. **Given** a suggestion exists, **When** the user looks at "Deeper examination", **Then** it
   is enabled and shows its expected time and cost (about 70 s, about $0.32 as measured on 13.11).
3. **Given** the app is open, **When** the user reads the note next to "Deeper examination",
   **Then** it says the fast pass handles ordinary buildings well but often misses cave
   outlines and doors in castles and other complex structures, and that the deep pass fixes
   most of that.
4. **Given** a suggestion exists, **When** the user clicks "Deeper examination" and it
   succeeds, **Then** the previous mask is replaced by the new one and the status line shows
   the deep pass's model, time, estimated cost and note.
5. **Given** a deep pass has finished, **When** the user clicks "Deeper examination" again,
   **Then** a new trace runs and replaces the mask; no earlier mask can be restored.

---

### User Story 3 - Staying in control while a pass runs or fails (Priority: P3)

A pass takes up to a minute or more and can fail for reasons outside the user's control. While
it runs the user sees that it is working and for how long. If it fails they are told what
happened and what to do, and anything they already had on screen is still there to download.

**Why this priority**: Each pass costs money and depends on an outside service. Without this
story the app works on a good day; with it, a bad day does not lose the user's work or leave
them guessing.

**Independent Test**: Trigger each failure cause in turn (refusal, usage or rate limit, missing
or invalid key, no network, timeout, unreadable response), with and without an earlier mask on
screen, and check the message and the state of the screen.

**Acceptance Scenarios**:

1. **Given** a pass is running, **When** the user looks at the screen, **Then** a progress
   indicator shows the elapsed time and neither pass button can be clicked.
2. **Given** a mask is on screen and a deep pass is running, **When** the user clicks "Accept
   mask", **Then** the mask on screen is downloaded and the running pass continues.
3. **Given** a pass ends without a usable answer, **When** the user reads the message,
   **Then** it says in plain language what happened and what they can do, with no stack trace
   or raw error dump.
4. **Given** a mask is on screen and a later pass fails, **When** the failure message appears,
   **Then** the earlier mask is still shown and can still be accepted.
5. **Given** a pass has failed, **When** the user reads the status line, **Then** the failed
   pass is not shown as a successful result with a cost.
6. **Given** a pass is running, **When** the user uploads a new image, **Then** the result of
   the running pass is discarded and never appears over the new image.
7. **Given** any pass has failed, **When** the user tries again or uploads another image,
   **Then** the app works normally without a restart.

---

### User Story 4 - Map size worked out by the model (Priority: P4)

The user uploads a map and clicks "Suggest walls" without counting squares. As part of that
same pass, the model works out how many squares wide and tall the map is, the app fills in the
map size, and the walls are traced on that grid. The user checks the size and corrects it if
it is wrong, which costs nothing (Story 5). On a map with no visible grid, the app says the
model could not find one and uses the size in the fields.

**Why this priority**: Counting squares by hand is the one tedious step left in Story 1, and a
wrong count shifts every wall in Roll20. The app is still usable without it, because the user
can always type the size.

**Independent Test**: Run the fast pass on each real map whose size is known, with the
"detect map size" option on and the fields untouched, and compare the filled-in size with the
true one. Do the same on a map with no grid and check the message and the fields.

**Acceptance Scenarios**:

1. **Given** a new upload, **When** the user looks at the map size, **Then** a "detect map
   size from the image" option is on and the fields show 25 x 25.
2. **Given** the option is on and the map has a visible square grid, **When** a pass succeeds,
   **Then** the map size fields show the size the model found, a note says it was detected
   from the image, and the mask is drawn on that grid.
3. **Given** the option is on and the model finds no grid, **When** the pass succeeds,
   **Then** the mask is shown using the size in the fields and a note says no grid was found
   and asks the user to check the size.
4. **Given** a new upload, **When** the user types a map size, **Then** the option turns off
   and the typed size is used for every pass and for the downloaded file.
5. **Given** the option is on, **When** a pass runs, **Then** working out the map size is
   part of that pass: there is no separate paid action, and its time and cost are inside the
   pass's expected and reported figures.
6. **Given** a pass has filled in a detected size, **When** the user runs "Deeper
   examination" without touching the option, **Then** the size on screen is used and is not
   detected again; if the user turns the option back on first, the deep pass detects it anew.

---

### User Story 5 - Correcting the map size without paying again (Priority: P5)

After seeing the suggestion, the user notices they typed the wrong number of squares. They
change the map size. The mask stays where it is over the image and the downloaded file uses
the new grid.

**Why this priority**: A wrong map size is an easy mistake and re-running a paid pass to fix a
typo would be wasteful. It is a convenience on top of the first three stories.

**Independent Test**: Get a suggestion at 25 x 25, change the size to 26 x 28, accept the
mask, and check that the file's map size is 26 x 28 and the walls sit over the same image
features as before.

**Acceptance Scenarios**:

1. **Given** a mask is on screen, **When** the user changes the map width or height, **Then**
   the mask stays on screen over the same parts of the image and no pass is run.
2. **Given** the map size was changed after a suggestion, **When** the user accepts the mask,
   **Then** the downloaded file states the new map size and its walls, portals and lights line
   up with the same image features as before the change.

---

### Edge Cases

- **Unsupported file type** (for example `.gif`, `.pdf`, or a renamed non-image file): rejected
  with a clear message; no pass can be started and nothing is sent to the provider.
- **File larger than 20 MB**: rejected with a clear message before any paid call.
- **Map size outside 1 to 200, empty, or not a whole number**: the pass buttons cannot start a
  pass until it is corrected, and a message says what the allowed range is.
- **Map with nothing to detect** (open field, no walls, doors or lights): the pass succeeds
  with an empty mask and says that nothing was found. An empty result is not a failure.
- **Map size that does not match the image's proportions** (grid cells would not be square):
  the app warns the user and lets them continue.
- **Map size changed while a pass is running**: the result is shown using the map size on
  screen when the pass finishes.
- **Map with no visible grid, or a faint or partly hidden one**: the model reports that it
  found no grid; the pass uses the size in the fields and the user is asked to check it.
- **Map with a hex or isometric grid**: treated as no grid found; only square grids are
  detected.
- **Detected size outside 1 to 200**: treated as no grid found.
- **Pass fails while the option is on**: the map size fields are left as they were.
- **Detected size is wrong**: the user types the right one; the mask stays over the same
  image features and no pass is run (Story 5).
- **A second upload while a pass is running**: the running pass's result is discarded (Story 3,
  scenario 6).
- **Very large map** (for example 200 x 200 squares): the pass runs as usual; the expected time
  and cost on the buttons are stated as typical values, not guarantees.
- **Session ends or the page is reloaded**: the image, mask and status are gone; nothing is
  kept.

## Requirements *(mandatory)*

### Functional Requirements

**Inputs**

- **FR-001**: The app MUST accept one map image per session as `.png`, `.jpg`/`.jpeg` or
  `.webp`, up to 20 MB.
- **FR-002**: The app MUST reject any other file type and any file over 20 MB with a clear
  message, before anything is sent to the provider and before any cost is incurred.
- **FR-003**: The app MUST let the user enter the map size as width and height in grid
  squares, pre-filled with 25 x 25, each a whole number from 1 to 200, and MUST NOT start a
  pass that would use a value outside that range.
- **FR-004**: The app MUST offer a "detect map size from the image" option, off by default
  for every new upload (a config value; changed from on by default on 13.11, because it adds
  about $0.03 per pass and missed on a map with a faint grid). When a pass runs with the option on, the model MUST work out the
  map's size in squares from the image as part of that pass, and the app MUST fill in the map
  size fields with it, say that it was detected, and use it for the mask.
- **FR-004a**: When the model finds no square grid, or finds a size outside 1 to 200, the
  pass MUST use the size in the fields and the app MUST tell the user no grid was found and
  ask them to check the size. This is not a failed pass.
- **FR-004b**: The map size MUST stay editable at all times. Typing a size MUST turn the
  option off, and a typed size MUST win over a detected one for every pass and for the
  downloaded file. A size already detected MUST NOT be detected again unless the user turns
  the option back on.
- **FR-004c**: Working out the map size MUST NOT be a separate paid action and MUST NOT
  happen outside a pass the user started. Its time and cost MUST be included in that pass's
  expected and reported figures.
- **FR-005**: When the user changes the map size while a mask exists, the app MUST keep the
  mask positioned over the same image features, MUST NOT run a pass, and MUST use the new map
  size in the downloaded file.

**Suggesting a mask**

- **FR-006**: A new upload MUST clear the previous image, mask and status, and MUST discard
  the result of any pass still running.
- **FR-007**: "Suggest walls" MUST run the fast pass on the uploaded image and show the result
  drawn over the map, with walls, portals and lights each visually distinct.
- **FR-008**: "Deeper examination" MUST be available only once a suggestion exists. It MUST
  trace the map again from scratch with the stronger model (not refine the existing mask) and
  replace the mask on screen.
- **FR-009**: "Deeper examination" MUST be repeatable; each run replaces the previous mask, and
  the app MUST NOT offer a way back to an earlier mask.
- **FR-010**: Each pass button MUST show its expected time and cost before it is clicked:
  values come from the config and are updated after each full reference evaluation (13.11:
  about 25 s and about $0.10 for the fast pass, about 70 s and about $0.32 for the deep pass,
  both including the map-size step).
- **FR-011**: After each successful pass the status line MUST show the model used, the time
  taken, the estimated cost and the model's own note on what it was unsure of.
- **FR-012**: A short note next to "Deeper examination" MUST tell the user when the deep pass
  is worth paying for: the fast pass handles ordinary buildings well but often misses cave
  outlines and doors in castles and other complex structures; the deep pass fixes most of
  that.
- **FR-013**: The app MUST tell the user, where they upload, that the image is sent to a
  third-party vision-model provider for analysis.

**What gets detected**

- **FR-014**: The mask MUST mark as a wall anything that blocks sight and movement: building
  walls, palisades, cave walls and cliffs. Furniture, rugs, trees, boulders and water MUST NOT
  be marked as walls.
- **FR-015**: The mask MUST mark doors and windows set in a wall as portals, as one type with
  no door/window distinction. An open gap with no door MUST be left as a gap.
- **FR-016**: The mask MUST mark each drawn, lit light source (torch, candle, lantern, brazier,
  campfire) as a light and classify it as small, medium or large.
- **FR-017**: Each light's radius and intensity in the downloaded file MUST come from a fixed
  lookup table keyed by its size tier, not from a per-light estimate.

**Accepting and downloading**

- **FR-018**: "Accept mask" MUST always be visible, enabled whenever a mask is on screen and
  disabled otherwise.
- **FR-019**: "Accept mask" MUST download the mask currently on screen as a Universal VTT
  file, with the extension the user chose: `.dd2vtt` or `.uvtt`. The content MUST be the same
  for both.
- **FR-020**: The downloaded file MUST contain the map image embedded at 70 px per grid
  square, the map size the user entered, and the walls, portals and lights shown on screen.
- **FR-021**: The downloaded file MUST import into Roll20 as a page background with its walls,
  portals and lights in place.

**While a pass is running**

- **FR-022**: While a pass is running the app MUST show a progress indicator with the elapsed
  time, and MUST prevent either pass button from being clicked.
- **FR-023**: While a pass is running, any mask already on screen MUST stay visible and MUST
  still be acceptable.

**Failure handling**

- **FR-024**: If a pass ends without a usable answer, the app MUST show a plain-language
  message saying what happened and what the user can do. This covers at least: the model
  refuses, a usage or rate limit is hit, the provider key is missing or invalid, the network
  is down, the request times out, and the response cannot be read.
- **FR-025**: The app MUST NOT crash or show a stack trace to the user in any of those cases,
  and MUST stay usable afterward without a restart.
- **FR-026**: After a failed pass, any earlier mask MUST stay on screen and remain acceptable.
- **FR-027**: The status line MUST NOT present a failed pass as a successful result with a
  cost.

**Privacy and access**

- **FR-028**: The provider key MUST come from the operator's configuration. The app MUST NOT
  ask the user for a key and MUST NOT display it.
- **FR-029**: The app MUST NOT require an account or login.
- **FR-030**: The app MUST NOT keep uploaded images, masks or downloaded files after the
  session ends.

### Key Entities

- **Map image**: the uploaded picture of the battlemap. Has a file type, a file size and pixel
  dimensions. One per session; a new upload replaces it.
- **Map size**: width and height in grid squares, worked out by the model during a pass or
  entered by the user; the user's value wins. Sets the grid of the
  downloaded file and can change without changing the mask's position over the image.
- **Mask**: the current suggestion for one map image: a set of walls, portals and lights,
  positioned relative to the image. At most one exists at a time; each successful pass
  replaces it.
- **Wall**: a line or curve that blocks sight and movement.
- **Portal**: a door or window set in a wall, with a position and a width along the wall.
- **Light**: a lit light source with a position and a size tier (small, medium, large).
- **Light tier table**: the fixed table that gives each size tier its radius and intensity.
- **Pass**: one analysis of the map image, fast or deep. Has a kind, the model used, the time
  taken, an estimated cost, the model's note, and an outcome: a mask, or a failure with its
  cause.
- **Export file**: the downloaded Universal VTT file: the map image at 70 px per grid square,
  the map size, and the mask's walls, portals and lights, under the chosen extension.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: Using only the fast pass, a user gets from upload to a downloaded file in under
  2 minutes.
- **SC-002**: On the reference building map, the downloaded file imports into Roll20 with fog
  of war following the walls and needs no manual fixes.
- **SC-003**: On the labeled reference building map, the fast pass reaches a wall-boundary F1
  of at least 0.95.
- **SC-004**: On the labeled reference maps, the deep pass reaches a wall-boundary F1 of at
  least 0.95 on the building map and at least 0.85 on the cave map, and finds more than half
  of the labeled doors on the building map.
- **SC-005**: 100% of paid actions show their expected time and cost before the click, and the
  actual time and estimated cost after a successful run.
- **SC-006**: For each of the six listed failure causes, the user sees a plain-language
  message, never a stack trace, and can start another pass or upload another map without
  restarting the app.
- **SC-007**: In every failure case tried with a mask already on screen, that mask is still on
  screen and downloadable afterward.
- **SC-008**: No rejected upload (wrong type, over 20 MB) and no invalid map size leads to a
  paid call.

- **SC-009**: On the project's real maps that have a visible square grid and a known size,
  the map size a pass works out (fast or deep; both use the same size step) is exactly
  right on at least 80% of them, and on a map
  with no grid the app reports that none was found instead of filling in a wrong size.

## Assumptions

- **One user at a time.** The operator and the user are usually the same person, on the
  operator's own machine. Concurrent users and access from the internet are not designed for.
- **Reference maps.** The "building map" is the labeled castle map and the "cave map" is the
  labeled mine map already used for the measurements this spec's thresholds come from. A
  separate published tavern map is used only for the Roll20 import check and is never
  redistributed.
- **Thresholds are regression floors.** They sit just under what was measured in one run per
  map (fast pass 0.96 on the building map; deep pass 0.99 and 0.88). Results vary between
  runs, so a single run slightly under a floor calls for a repeat before it counts as a
  regression.
- **"Most castle doors"** is read as more than half of the labeled doors on the building map.
- **Expected time and cost** on the buttons are typical values from those measurements. Actual
  values depend on the map and on the provider's prices at the time.
- **Estimated cost** is computed from the provider's reported usage and a price list kept in
  configuration. It is an estimate, not a bill.
- **A pass that produces nothing usable** may still have cost something at the provider. The
  app does not report it as a successful result; it does not promise that it was free.
- **Time limit per pass.** A fast pass with no answer after 60 seconds, or a deep pass after
  180 seconds, counts as timed out. (Set in planning; the first draft said 5 minutes.)
- **Map size and image proportions.** If the entered map size would make grid cells
  non-square, the app warns and continues; it does not block.
- **Changing the map size** rescales positions only. Each light keeps its size tier.
- **Roll20 is the only tested target.** Other tools that read Universal VTT files may work
  but are not checked.
- **Grid detection target.** The 80% in SC-009 was a first target. Measured on 13.11: Opus
  4 of 4 runs right on maps with a grid, Sonnet 1 of 3, so the size step runs on Opus in both
  passes and the target stands.
- **Grid detection covers square grids only**, and gives a whole number of squares in each
  direction. It does not correct a map whose image is cropped mid-square.
- **Grid detection is done by the vision model, inside a pass**, not by a separate local
  step. The expected time and cost on the buttons were measured with the map size given, so
  they are to be measured again once the model also works out the size.
- **Out of scope:** editing the mask by hand; user accounts or
  login; keeping uploads or results after the session; output formats other than Universal
  VTT; undo back to an earlier mask.
- **Dependencies:** a working internet connection, and an account with the vision-model
  provider with a key the operator has put in configuration.
