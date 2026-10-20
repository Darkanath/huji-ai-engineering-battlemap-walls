# Labeling rules

These rules define what the model learns. They apply to every dataset: synthetic maps, Dungeondraft
maps and the hand-traced test set. If a map breaks a rule, fix the map, not the rule. If a rule
turns out to be wrong, change it here first, then regenerate the affected masks.

## Classes

| Id | Class | Meaning |
| --- | --- | --- |
| 0 | background | Everything else: floor, terrain, furniture, open gaps |
| 1 | wall | Blocks both sight and movement |
| 2 | portal | A door or window set in a wall |

There is one portal class for doors and windows. Universal VTT portals have no door/window type,
and Roll20 imports every portal as a door, so the GM switches the few windows by hand.

## Wall (class 1)

A wall is anything that blocks **both sight and movement**.

**Walls:** building walls (stone, brick, wood, plaster), palisades, cave walls, cliff faces.

**Not walls:**

- Furniture, counters, bookshelves, crates, barrels, statues, rugs.
- Trees, boulders, bushes, water, lava, pits, chasms.
- Things that block only one of the two: low fences, railings and rubble (block movement, not
  sight), curtains (block sight, not movement).
- The map border. The edge of the image is not a wall unless a wall is drawn there.

## Portal (class 2)

A portal is a door or window **set in a wall**.

- **Doors:** wooden, iron, double doors, gates in a palisade, portcullises.
- **Windows:** any see-through opening in a wall that blocks movement (glazed, barred, shuttered).
- A portal's open or closed state does not matter: label it either way.
- Every portal in the .dd2vtt is labeled, whatever its `freestanding` flag. Dungeondraft sets
  `freestanding: true` on ordinary doors that sit in walls (10 of the 14 portals on the demo map),
  so the flag does not mean "not in a wall".

**Not portals:**

- **A gap with no door is just a gap.** Archways, doorless doorways, broken walls and cave
  openings are background. The model has to learn that an opening is not a broken wall, and
  post-processing keeps such gaps open.
- Secret doors and traps. They are not visible in the image by design.
- Stairs, ladders and trapdoors: they connect floors, not rooms on one floor.

## How labels are drawn

Labels come **only** from `.dd2vtt` files (`data/rasterize.py`). Never use `.dungeondraft_map`
source files.

- Walls are `line_of_sight` plus `objects_line_of_sight` polylines, drawn as a band **0.25
  squares** wide along the centerline.
- Portals are their `bounds` segment, drawn **0.30 squares** wide, on top of the walls. This way a
  portal always wins over the wall it sits in.
- **Label width is fixed, whatever the drawn wall width.** A .dd2vtt only stores centerlines, and
  post-processing skeletonizes the mask back to centerlines anyway. A consistent band is an easier
  target than one that changes with the art style. The images still have to show many wall
  widths, so the synthetic generator varies them.
- Masks are stored as **PNG** (exact class ids). Images are stored as JPEG.

## Making Dungeondraft maps

- **Map size:** 25×25 squares unless the layout needs otherwise.
- **Export:** Universal VTT with the **Roll20 grid preset** (70 px per square).
- **Style variants:** export each layout **3 times** with different wall styles, floor textures,
  and lighting or grid on or off. Name them `<layout>_<variant>.dd2vtt`, for example
  `dd01_a.dd2vtt`, `dd01_b.dd2vtt`, `dd01_c.dd2vtt`. The 3 variants of one layout always go in
  the same split.
- **Content:** walls, doors, windows, at least one doorless opening, and a scatter of furniture as
  distractors. No detailing needed.
- **Shadows:** do not turn on shadow casting for furniture or other objects. Dungeondraft exports
  shadow-casting objects to `objects_line_of_sight`, which the rasterizer labels as walls, so a
  shadow-casting table would become a wall in the mask.
- **Check every export:** run `python -m data.rasterize <map>.dd2vtt` and look at the
  `_preview.jpg`. Red must cover only walls and magenta only doors and windows.

## Hand-tracing the test set

Test maps are third-party or hand-made images with no .dd2vtt, so their labels are traced by hand
and saved as .dd2vtt. The same rules apply:

- Trace each wall along its **centerline**, as one polyline per continuous run of wall.
- End the wall at each side of a doorless opening, so the gap stays open.
- Place each door or window as a portal across the wall, with its `bounds` from jamb to jamb.
- Check the trace with the rasterizer preview, the same way as Dungeondraft maps.
- Published third-party maps stay in the test set only and are never redistributed.

## Edge cases log

When a map raises a case these rules don't cover, decide it, add it here with the map name, and
apply it everywhere.

| Case | Decision | Example map |
| --- | --- | --- |
| Door flagged `freestanding` but sitting in a wall | Portal | `demo-training-map` |
| Several portals stacked at the same position | One portal; the mask is the same either way. Deduplicate before counting portals or writing a .dd2vtt | `dd01_a`, `dd01_b` |
