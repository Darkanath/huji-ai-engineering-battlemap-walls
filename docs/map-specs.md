# Dungeondraft map specifications

What to build for the Dungeondraft set `dd04`–`dd18`: 15 layouts × 4 variants = 60 exports. With
`dd01`–`dd03` that makes 18 layouts, inside the plan's 15–20. The rules for what counts as a wall,
portal or light are in [labeling-rules.md](labeling-rules.md); finished maps go in the log in
[dungeondraft-maps.md](dungeondraft-maps.md).

## What the first three layouts lack

`dd01`–`dd03` are clean but easy: only right-angle walls, a few large rooms, wide empty margins,
few distractors next to walls, and no lights. A model trained only on them would learn "a dark line
around a big rectangle is a wall". Each new layout targets one or more of the gaps below.

| Gap | Layouts that cover it |
| --- | --- |
| Diagonal and curved walls | dd08, dd11, dd18 |
| Irregular, thick or free-form walls (caves, cliffs) | dd06, dd07 |
| Broken walls, many doorless gaps | dd16, dd06 |
| Objects that look like walls (shelves, counters, pews, fences, rails) | dd04, dd05, dd09, dd13, dd15 |
| Many small rooms, thin interior walls, many doors | dd17, dd10 |
| Wide and double doors, gates, portcullis | dd08, dd12, dd15 |
| Windows of every kind (glass line, barred, arrow slit) | dd05, dd08, dd09, dd17 |
| Lights of all three tiers, wall-mounted and free-standing | all; large tier in dd08, dd12, dd15 |
| Glow without a light (lava, crystals, magic circles) | dd11, dd09, dd07 |
| Outdoor layouts | dd12, dd13 |
| Map size other than 25×25 | dd13 (30×20), dd14 (20×30) |

Themes come in pairs (caves, outdoor, domestic, religious, fortified), so each kind of map is
likely to land in training even after the split takes about 3 layouts for validation and 3 for
test.

## Every layout must have

- **Size:** 25×25 squares unless the layout says otherwise; Roll20 grid preset (70 px per square).
- **Fill the map:** walls come within 2–3 squares of the edge on at least two sides. No large
  empty margins: they only add easy background.
- **Walls:** at least 5 rooms or areas, with interior walls as well as outer walls.
- **Portals:** at least 5 doors, including 1 double door, and at least 2 windows wherever the
  theme has building walls.
- **Gaps:** at least 2 doorless openings (archway, doorless doorway or broken wall), each 1–3
  squares wide.
- **Lights:** at least 3 lit light sources covering at least 2 tiers, at least 1 of them
  wall-mounted (on the room side of the wall, not on it). Each one is a sprite plus a Dungeondraft
  light with range 8 (small), 12 (medium) or 16 (large).
- **Unlit fixtures:** at least 2 (unlit torch, cold brazier, empty fireplace) as negatives for
  the light class.
- **Distractors:** at least 10 objects, at least 3 of them **against or parallel to a wall**
  (shelf, counter, bed, bench, crates in a row). This is where the model learns "next to a wall
  is not a wall".
- **Shadows off** on every object (otherwise they become walls in `objects_line_of_sight`).
- **Check** each export with `python -m data.rasterize` before making the next variant.

## The four variants

Every layout is exported four times. **Walls, portals, lights (position and `range`) and object
positions stay identical** in all four; only the look changes. Paint the variants in order and
re-export after each change.

| Variant | Walls | Floor | Grid | Lighting | Purpose |
| --- | --- | --- | --- | --- | --- |
| `a` | The theme's natural style | The theme's natural floor | On | Normal daylight ambient | The base map |
| `b` | **Another style**, ideally another thickness | Same as `a` | On | Same as `a` | Wall appearance alone changes |
| `c` | Same as `b` or `a` | **Busy pattern**: tiles, flagstones, parquet, planks with strong lines | On | **Dark** ambient (night or dungeon), so lights glow strongly | Floor lines that look like thin walls; strong glows |
| `d` | A third style: thin and dark, or a very light one that has little contrast with the floor | A third floor, different from every other layout's `d` | **Off** | Export with **Lighting off** (no glow at all, only the sprites) | Hardest look; no grid for grid detection |

- Light **intensity and color** may change between variants (they are not labeled); **range may
  not**, because it sets the tier.
- Across layouts, use different floors in each `a` too. The current `c` variants all share one
  grey floor: don't repeat that.
- If a theme has no second wall style that fits (caves, cliffs), change the wall color or
  texture in `b` instead. The base software has only 5 wall styles, but walls are colorable, so
  a recolor counts as a style.
- Lighting off in the export sets `environment.baked_lighting` to `false` in the .dd2vtt (as in
  `dd01_a`); the other variants have `true`. Check on the first `d` export that `lights` is still
  filled with lighting off.

## Tool checks

Checked against the Dungeondraft documentation and the existing exports (21.10). Dungeondraft is
not installed where Claude can reach it, so the asset library could not be listed; check those
items in the app.

**Confirmed:**

| Feature the spec needs | How | Source |
| --- | --- | --- |
| Curved walls | Hold Shift between points in the Building or Wall tool | Encounter Library, design tools |
| Round rooms and towers | Building tool, circle shape | Encounter Library, design tools |
| Diagonal walls | Polygon building or Wall tool, points at any angle | Encounter Library, design tools |
| Caves | Cave brush ("Dig Cave", "Blast Open" for openings) | Encounter Library, design tools |
| Doors and windows at any angle | Portal tool; anchored (snaps to walls) or freestanding with rotation | Encounter Library, design tools |
| Lights with range, intensity, color, style, shadows | Light tool; lights are placed separately from objects | Encounter Library, light tool |
| Dark or bright ambient (variants `c`, `d`) | Environmental Lighting color and opacity | Encounter Library, light tool |
| Grid and lighting off in the export | Export dialog toggles; lighting off shows as `baked_lighting: false` | Encounter Library, export; `dd01_a` |
| Lights in the .dd2vtt | Universal VTT stores light sources; `range` is read as grid squares by importers | Dungeondraft encyclopaedia; Arkenforge format notes |

**Check on the first export that uses them:**

- **Cave walls** (`dd06`): the rasterizer preview must show red along the cave walls. The format
  lists caves separately from walls, so make sure they end up in `line_of_sight`. If they don't,
  `data/rasterize.py` needs to read them too.
- **Curved walls** (`dd08`): the red band must follow the curve, not cut across it.
- **Light range** (`dd04_a`): open the .dd2vtt and check that a light you set to 8 shows
  `"range": 8`. If Dungeondraft's slider uses another unit, the tier ranges in `LIGHT_TIERS`
  change, not the maps.

**Assets to find in the Default pack** (Objects tool, pack name "Default"; about 1,500–1,800
objects). If one is missing, swap the item for one that exists rather than adding an asset pack:
third-party packs have their own licenses, and some limit use.

- Lights: wall torch, candle, candelabra, lantern (hanging and standing), brazier, campfire, fire
  pit, fireplace, forge.
- Distractors: bookshelf, bar counter, pew, pillar, mine-cart rail, crates, sarcophagus, tent,
  fence, rubble, crystal, magic circle.
- Portals: double door, portcullis or gate, barred door, barred window.

## Dungeon Alchemist as a second source

Dungeon Alchemist (DA) can export Universal VTT (.dd2vtt) with walls, portals and lights, so its
maps fit the pipeline without new code in the rasterizer. It is worth using for some layouts:

- **Fast:** rooms are furnished automatically, so dense distractors and light sources cost little.
- **A second art style:** DA renders 3D-looking maps with real shadows. Many published maps look
  like this, so it helps on the hard test set, and it keeps the model from learning only
  Dungeondraft's look.

**What has to be handled:**

- **Camera:** export with the **Orthographic (Top Down)** camera, so walls sit on the grid lines.
  A perspective view would likely not line up with the wall data.
- **Light tiers:** DA sets each light's radius by its asset type and an intensity slider, and
  users reported in 2024 that the radii don't follow tabletop values. The `range` values will not match 8 / 12 / 16, so the
  rasterizer rejects the file as it is. A small script is needed to rewrite each DA light's
  range to its tier (and drop lights from things the rules say are not lights, like glowing
  crystals) before the file goes in `data/raw/`. Light colors are always set in DA; color is
  not labeled, so that doesn't matter.
- **Light glow:** DA's default writes lights into both the image and the VTT data. A "VTT data
  only" option leaves the glow out of the image, which plays the role of Dungeondraft's
  lighting-off export.
- **Resolution:** the DPI setting is pixels per square. Use 70 if DA accepts it; any whole
  number works, because the rasterizer rescales to 70. Keep it low: DA files reach 100 MB at
  300 DPI.
- **Walls:** DA walls are thick and drawn in 3D. Check on the first export that the red band
  sits on the visible walls.
- **Variants:** a DA restyle may re-roll the furniture and lights. That is fine (every export
  has its own labels), but the **walls and portals must stay the same**, so all variants of a
  layout still share one mask outside the lights.
- **License:** DA's terms allow personal and limited commercial use of what you make and say
  nothing about training models. The project trains on these maps and never redistributes them,
  the same as Dungeondraft maps.

**Pilot first.** Make one DA layout (`da01`, a furnished interior), export it, run the
rasterizer and look at the preview before planning more. If walls, portals and lights land right,
DA layouts can replace some of `dd09`–`dd18` below (the furnished interiors: temple, prison,
smithy, townhouse, crypt) and keep Dungeondraft for what needs precise control (curves, caves,
ruins, outdoor). DA maps go in `data/raw/dungeon_alchemist/` as `daNN_<variant>.dd2vtt` and
follow the same split rule by layout.

## The layouts

Light counts are lit sources per tier: S small (candle, torch, sconce), M medium (lantern,
brazier, campfire, fireplace), L large (bonfire, fire pit, forge).

### Week 2: dd04–dd08

**dd04 · Tavern and inn** (wood). Ground floor of an inn: common room, kitchen, storeroom, 3–4
small guest rooms along a corridor.
- Portals: double front door, back door, a door per guest room, 4+ glass windows on outer walls.
- Gaps: open arch between common room and kitchen.
- Lights: S 4 (wall sconces, candles on tables), M 2 (fireplace, kitchen hearth). Unlit: 2
  sconces in the storeroom.
- Targets: **bar counter running parallel to a wall**, shelves behind it, benches along walls.

**dd05 · Manor library and study** (plaster or brick). Library hall, reading room, study, a
narrow gallery.
- Portals: double door into the library, 3+ doors, 6+ glass windows drawn as thin lines.
- Gaps: two doorless openings between library bays.
- Lights: S 4 (candelabras, desk candles), M 2 (fireplace, standing lantern). Unlit: 2.
- Targets: **bookshelves lining the walls and in free-standing rows**, the hardest "looks like a
  wall" case. Rugs with straight borders.

**dd06 · Natural cave** (cave walls, free-form tool). Winding cave system with 4–5 chambers and
narrow passages.
- Portals: one wooden door into a chamber walled off with masonry; otherwise none.
- Gaps: most passages are open (caves have gaps, not doors), 3+ of them.
- Lights: S 2 (torches on the cave wall, room side), M 2 (campfires). Unlit: a burnt-out campfire.
- Targets: **irregular thick walls**, boulders and stalagmites (not walls), an underground pool.

**dd07 · Mine** (cave walls plus carved stone). Mine tunnels with a timber-shored shaft, an
office and a storeroom.
- Portals: 3+ doors in the carved section, 1 double door (ore store).
- Gaps: 3+ open tunnel mouths.
- Lights: S 3 (wall torches), M 3 (hanging lanterns, a brazier). Unlit: 2 lanterns.
- Targets: **mine-cart rails** (long thin lines, not walls), timber beams, crates and ore piles,
  a glowing crystal vein (glow, not a light).

**dd08 · Castle keep** (thick stone). Keep with **round corner towers**, a courtyard, a
gatehouse and a great hall.
- Portals: **portcullis** and double gate in the gatehouse, 4+ doors, 4+ arrow slits (very thin
  windows).
- Gaps: open arches between courtyard and great hall.
- Lights: S 3 (wall torches), M 2 (braziers at the gate), L 1 (courtyard fire pit). Unlit: 2.
- Targets: **curved walls**, very thick walls, a courtyard (outdoor area inside walls).

### Week 3: dd09–dd13

**dd09 · Temple** (stone). Nave with side aisles, sanctum, vestry, bell-tower base.
- Portals: large double door, 3+ doors, 4+ stained-glass windows.
- Gaps: arches between nave and aisles.
- Lights: S 5 (candles, altar candles), M 2 (braziers). Unlit: 2 candle stands.
- Targets: **rows of pews** (parallel lines), **rows of pillars** (not walls, see the edge cases
  below), a glowing magic circle on the floor (glow, not a light).

**dd10 · Prison** (stone, thin walls between cells). Cell block of 6–8 small cells, guard room,
interrogation room.
- Portals: a barred door on every cell, 3+ wooden doors, 2 barred windows.
- Gaps: one open corridor junction.
- Lights: S 4 (wall torches in the corridor), M 1 (guard room brazier). Unlit: torches in empty
  cells.
- Targets: **many small rooms and many doors**, thin walls, beds and buckets against walls.
  Cell fronts are solid walls with a barred door, not full rows of bars (see the edge cases below).

**dd11 · Wizard tower** (stone or brick). **Octagonal** main room, 45° corridors, round study,
laboratory.
- Portals: 4+ doors set in diagonal walls, 3+ windows in diagonal walls.
- Gaps: 2 doorless openings.
- Lights: S 3 (candles), M 2 (lanterns). Unlit: 1 lantern.
- Targets: **diagonal walls and portals at 45°**, glowing crystals and a glowing potion table
  (glow, not lights), shelves on diagonal walls.

**dd12 · Fortified camp** (palisade, outdoor). Palisade ring with a gate, tents, a command
building, a corral.
- Portals: palisade gate (wide double), 2+ doors on the command building, 2 windows.
- Gaps: a breach in the palisade, 2 squares wide.
- Lights: S 3 (torches on poles, free-standing), M 3 (campfires), L 1 (central bonfire).
  Unlit: a cold fire pit.
- Targets: **palisade as wall**, **fences around the corral (not walls)**, tents (background, see the edge
  cases below), trees, carts.

**dd13 · Village street** (wood and plaster, outdoor), **30×20 squares**. A street with 4–5
small houses and shops on both sides.
- Portals: a door per house (one double, for a shop), 6+ windows.
- Gaps: an open shop front (counter, no wall), a doorless shed.
- Lights: M 4 (street lanterns on posts), S 2 (lanterns by doors, as wall lights). Unlit: 1
  street lantern.
- Targets: **garden fences and low walls** (not walls), a well, market stalls, a non-square map.

### Week 4: dd14–dd18

**dd14 · Sewer** (brick), **20×30 squares**. Sewer channels with walkways, a cistern, a
smugglers' room.
- Portals: 3+ doors, 2 iron gates (doors), 2 barred grates in walls (windows).
- Gaps: 3+ open channel junctions.
- Lights: S 3 (wall torches), M 1 (smugglers' lantern). Unlit: 2. Dark ambient in every variant
  except `d`.
- Targets: **water channels next to walls** (the water is not a wall), walkway edges, narrow
  corridors, a non-square map.

**dd15 · Smithy and warehouse** (wood and stone). Forge, workshop, warehouse, yard.
- Portals: **wide barn double doors** (2–3 squares), 3+ doors, 3+ windows.
- Gaps: an open side of the forge onto the yard.
- Lights: L 1 (forge), M 2 (braziers), S 2 (wall lanterns). Unlit: a cold second forge.
- Targets: **rows of stacked crates** and racks (wall-like lines), workbenches against walls, a
  very wide portal.

**dd16 · Ruins** (broken stone, partly outdoor). Ruined abbey: half-standing walls, rubble,
overgrowth.
- Portals: 2 surviving doors, 2 windows.
- Gaps: **5+ breaches and broken wall ends**; walls end at the broken edge, the rubble is not a
  wall.
- Lights: M 2 (campfires), S 1 (torch on a standing wall). Unlit: 1.
- Targets: **gaps that must stay gaps**, rubble, trees growing in rooms, vines over walls.

**dd17 · Townhouse** (plaster, thin interior walls). A dense two-wing house with 10+ small rooms.
- Portals: **10+ doors**, 1 double door, 6+ windows.
- Gaps: 2 open arches.
- Lights: S 5 (candles, wall sconces), M 2 (fireplaces). Unlit: 2 sconces.
- Targets: **thin walls close together**, beds, wardrobes and dressers against walls, rugs with
  borders.

**dd18 · Crypt** (stone). Catacombs: corridors with burial alcoves, a round central chamber,
an ossuary.
- Portals: 3+ doors, 1 double door to the central chamber.
- Gaps: 3+ alcove openings (open niches in the wall, which are gaps).
- Lights: S 4 (candles in alcoves), M 2 (braziers). Unlit: 3 candles.
- Targets: **wall niches** (the wall bends around them), **sarcophagi in rows**, a **round
  chamber** (curved walls).

## Edge cases decided for this set (21.10)

These are also in the edge cases log in [labeling-rules.md](labeling-rules.md).

| Case | Decision | Needed for |
| --- | --- | --- |
| Pillars and columns | Background, like statues. A pillar class stays a stretch goal | dd09, dd08 |
| Tents | Background: they are objects, not built walls | dd12 |
| Rows of cell bars | Avoid: draw cell fronts as walls with a barred door portal | dd10 |
| Open shop front with a counter | Gap (background); the counter is furniture | dd13 |
| Arrow slits | Portal (a very thin window) | dd08 |

## Time

About 25–30 minutes per layout plus 10 minutes for the three restyles and four exports: roughly
40 minutes per layout, so about 3.5 hours a week for weeks 2–4, as in the roadmap (`dd04`–`dd08`
in week 2, `dd09`–`dd13` in week 3, `dd14`–`dd18` in week 4). If time runs short, drop layouts
from the end of each week's list, but keep at least one of each pair.
