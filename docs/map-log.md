# Map log

Every real map made for the project: Dungeondraft maps in `data/raw/dungeondraft/` and Dungeon
Alchemist maps in `data/raw/dungeon_alchemist/` (both gitignored), named
`<layout>_<variant>.dd2vtt` as set in [labeling-rules.md](labeling-rules.md). All style variants
of one layout always go in the same split. What each new layout should contain is in
[map-specs.md](history/map-specs.md).

This log keeps what the file names leave out, for the data summary and the error analysis. Splits
are in `data/processed/manifest.csv` (`python -m data.manifest`). The first build (21.10) put
`dd01` in train, `dd02` in test and `dd03` in val, and `da01` in train; splits never change after
that.

## Dungeondraft maps

All are 25×25 squares at 70 px per square.

| File | Layout | Variant | Walls | Objects | Wall / portal share | Lights | Notes |
| --- | --- | --- | --- | --- | --- | --- | --- |
| `demo-training-map` | demo | - | stone | none | 7.4% / 0.6% | 0 | Test fixture; keeps its name because the tests use it |
| `dd01_a` | dd01 | a | wood | few | 4.8% / 0.3% | 0 | Buildings on dirt; bathtub, stove, bushes. 3 portals stacked at (5, 20.5) |
| `dd01_b` | dd01 | b | other wall style, other floor | few | 4.8% / 0.3% | 0 | One door 1 px off from `a` (142 mask pixels); same stacked portals as `a` |
| `dd01_c` | dd01 | c | other wall style, grey patterned floor | few | 4.8% / 0.3% | 0 | Same stacked portals as `a` |
| `dd02_a` | dd02 | a | wood | many | 5.1% / 0.2% | 0 | River across the top; books, rugs, cobwebs as distractors |
| `dd02_b` | dd02 | b | other wall style | many | 5.1% / 0.2% | 0 | Floor, lighting and grid as `a` |
| `dd02_c` | dd02 | c | other wall style, grey patterned floor | many | 5.1% / 0.2% | 0 | Lighting and grid as `a` |
| `dd03_a` | dd03 | a | stone | none | 5.4% / 1.1% | 0 | Many windows (23 portals) |
| `dd03_b` | dd03 | b | other wall style | none | 5.4% / 1.1% | 0 | Floor, lighting and grid as `a` |
| `dd03_c` | dd03 | c | other wall style, grey patterned floor | none | 5.4% / 1.1% | 0 | Lighting and grid as `a` |
| `dd01_d` | dd01 | d | thin dark walls, parquet floor, **no grid** | few | 4.8% / 0.3% | 0 | Parquet forms a square pattern: a hard case for grid detection. Same stacked portals as `a` |
| `dd02_d` | dd02 | d | thin dark walls, grey concrete floor, **no grid** | many | 5.1% / 0.2% | 0 | |
| `dd03_d` | dd03 | d | thin dark walls, wooden plank floor, **no grid** | none | 5.4% / 1.1% | 0 | Glass windows are thin lines in the wall, as in `a` |
| `dd04_a` | dd04 | a | wood, parquet floor | many | 3.5% / 1.0% | 4 / 2 / 0 | Tavern and inn. 23 portals (7 doors, 1 double front door 3 squares wide, 15 windows), diagonal wall, kitchen arch and storeroom opening as gaps, 2 unlit sconces in the storeroom. Light share 0.3% |
| `dd04_b` | dd04 | b | thin dark hatched walls, floor as `a` | many | 3.5% / 1.0% | 4 / 2 / 0 | |
| `dd04_c` | dd04 | c | walls as `b`; herringbone, flagstone and tile floors | many | 3.5% / 1.0% | 4 / 2 / 0 | Dark ambient (`ff8b7777`), strong glows. Tile lines in the common room look like thin walls |
| `dd04_d` | dd04 | d | grey stone walls, grey cobbled floor, **no grid, lighting off** | many | 3.5% / 1.0% | 4 / 2 / 0 | First export with `baked_lighting: false` and lights: `lights` is still filled |
| `dd05_a` | dd05 | a | cave walls (grey rock), masonry side room | few | 8.3% / 0.0% | 2 / 2 / 0 | Natural cave: 5 chambers, winding passages, many open gaps, underground pool; 1 door into the masonry room (portal share 0.05%). Boulders, stalagmites, burnt-out campfire (no light). A stray cave-wall dot (0.2 squares) at (18.5, 10.7), drawn and labeled as wall |
| `dd05_b` | dd05 | b | orange-rimmed cave wall style, floor as `a` | few | 8.3% / 0.0% | 2 / 2 / 0 | |
| `dd05_c` | dd05 | c | grey rubble cave walls, cracked stone floor | few | 8.3% / 0.0% | 2 / 2 / 0 | The rubble is drawn outside the cave line, so the wall band covers its inner edge |
| `dd05_d` | dd05 | d | solid black cave walls, sand floor, **no grid, lighting off** | few | 8.3% / 0.0% | 2 / 2 / 0 | |
| `dd06_a` | dd06 | a | cave walls (grey rock), carved stone side room with flagstone floor | some | 7.2% / 0.2% | 3 / 3 / 0 | Mine: rail tunnels leaving the map on three sides, a junction, 2 ore carts, crates. 4 portals: a double gate (2 squares) on the rails, 2 cave doors, 1 door at the left map edge. 2 unlit fixtures. Purple crystals with no light (glow, not a light). Two cave-wall dots under 0.1 square at (18, 20) and (18.9, 14.7), invisible |
| `dd06_b` | dd06 | b | other cave wall style, floor as `a` | some | 7.2% / 0.2% | 3 / 3 / 0 | |
| `dd06_c` | dd06 | c | other cave wall style, cracked stone floor, **dark ambient** (`ff8b7777`) | some | 7.2% / 0.2% | 3 / 3 / 0 | |
| `dd06_d` | dd06 | d | other cave wall style, grey floor, **no grid, lighting off** | some | 7.2% / 0.2% | 3 / 3 / 0 | |
| `dd07_a` | dd07 | a | thick stone, 4 round corner towers, grass courtyard | some | 7.8% / 0.8% | 3 / 2 / 1 | Castle keep. 17 portals: 2 portcullises in the gatehouse, 4 arrow slits (0.8 squares), a double door into the great hall (2 portals), 1 door on the small building, 8 tower doors. Fire pit in the courtyard is the first large light. Pillars and a table in the great hall; a post-and-rope fenced pen (not a wall). Unlit wall torches in 3 towers. No doorless gaps |
| `dd07_b` | dd07 | b | other wall style | some | 7.8% / 0.8% | 3 / 2 / 1 | |
| `dd07_c` | dd07 | c | other wall style and floors, **dark ambient** (`ff8b7777`) | some | 7.8% / 0.8% | 3 / 2 / 1 | |
| `dd07_d` | dd07 | d | other wall style and floors, **no grid, lighting off** | some | 7.8% / 0.8% | 3 / 2 / 1 | |
| `dd08_a` | dd08 | a | stone, octagonal tower inside a thick stone outer wall, grass | some | 8.1% / 0.5% | 3 / 2 / 0 | Wizard tower: 45° walls, two curved rooms. 12 portals, all diagonal: 8 on the outer faces (4 doors 1 square, 4 windows 0.75 squares), 4 interior doors. Outer wall has 2 doorless gaps. Potion shelf with no light (glow, not a light); 1 unlit lantern. The medium light in the center is a floor lantern (confirmed), a small sprite inside its label disc |
| `dd08_b` | dd08 | b | other wall style | some | 8.1% / 0.5% | 3 / 2 / 0 | |
| `dd08_c` | dd08 | c | brick walls, brown floor, **dark ambient** (`ff8b7777`) | some | 8.1% / 0.5% | 3 / 2 / 0 | |
| `dd08_d` | dd08 | d | grey stone walls, blue-grey floor, **no grid, lighting off** | some | 8.1% / 0.5% | 3 / 2 / 0 | |

All `b`, `c` and `d` variants have the same walls and portals as their `a` (masks identical, except the
1 px door in `dd01_b`). Share of pixels that change away from the walls, compared with `a`:
`dd01_b` 23%, `dd02_b` 3%, `dd03_b` 2% (wall style only); every `c` 27–32% (new floor); `d` 13–36%
(new floor, no grid). The `c` variants share one grey patterned floor; the `d` variants each
have their own floor and no grid.

**Lights (21.10):** none of these exports has lights (`lights` is empty in every file), and none
draws a lit light source (`dd01` has an unlit stove), so the empty list is the correct label. They
stay as they are, as lights-free maps. From `dd04` on, the Lights column gives the count per tier
(small / medium / large).

`dd04` (21.10): Dungeondraft writes `range` in grid squares (a light set to 8 shows `"range": 8`),
so the tier ranges stand. All four variants have identical walls, portals and lights.

`dd05` (3.11): the first cave map. Dungeondraft writes cave walls to `line_of_sight` (7 polylines,
`objects_line_of_sight` empty), so the rasterizer reads them with no change. Wall share 8.3%,
higher than the building maps (3.5–5.4%), because cave outlines are long and winding. Split: train.

`dd06` (3.11): the first export put three doors in as hairlines, with almost nothing drawn at the
map edge; the re-export draws a door there and adds a carved stone room. Dungeondraft's door art
is a thin line across the opening, as wide as the wall (as in `dd04`), so the label band is wider
than the drawing on every Dungeondraft door. Mine-cart rails, long and thin, carry no label.
Split: train. With 6 layouts the Dungeondraft splits are 4 / 1 / 1; val gets its second layout as
more come in.

`dd07` (3.11): the round towers confirm that the wall band follows curved walls. The first export
drew the fenced pen with the wall tool, so it came out as a closed wall loop; the re-export draws
the fence without a wall (low fences block movement, not sight: not walls). Split: train.

`dd08` (3.11): diagonal walls and portals at 45° label cleanly: the bands follow the walls. Split:
train, which makes the Dungeondraft splits 6 / 1 / 1 with `dd04`–`dd08` done. By the split rule
the next layout (`dd09`) goes to val.

The next layouts, `dd04`–`dd13`, follow [map-specs.md](history/map-specs.md).

## Dungeon Alchemist maps

In `data/raw/dungeon_alchemist/` (originals in `original/`, lights converted with
`data.retier_lights`; see [map-specs.md](history/map-specs.md)). 25×25 squares at 72 px per square. The
next layouts, `da02`–`da06`, follow [map-specs.md](history/map-specs.md).

| File | Layout | Variant | Look | Wall / portal / light share | Lights (S / M / L) | Notes |
| --- | --- | --- | --- | --- | --- | --- |
| `da01_a` | da01 | a | Tavern on grass, grid, lights in the image | 2.7% / 0.8% / 0.8% | 20 / 3 / 0 | Pilot. Building covers about 16×13 squares; 5 double doors (2 portals each), 7 windows |
| `da01_d` | da01 | d | Same, no grid, lights in VTT data only | 2.7% / 0.8% / 0.8% | 20 / 3 / 0 | Same walls, portals and lights as `a` |
