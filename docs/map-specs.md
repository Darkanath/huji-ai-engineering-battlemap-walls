# Map specifications

What to build for the real-map datasets: 10 new Dungeondraft layouts (`dd04`–`dd13`) and 5 new
Dungeon Alchemist layouts (`da02`–`da06`), each exported as 4 variants, so 60 exports. With
`dd01`–`dd03` and the pilot `da01` that makes 19 layouts, inside the plan's 15–20. The rules for
what counts as a wall, portal or light are in [labeling-rules.md](labeling-rules.md); finished
maps go in [map-log.md](map-log.md).

## What the first maps lack

`dd01`–`dd03` are clean but easy: only right-angle walls, a few large rooms, wide empty margins,
few distractors next to walls, and no lights. A model trained only on them would learn "a dark line
around a big rectangle is a wall". Each new layout targets one or more of the gaps below.

| Gap | Layouts that cover it |
| --- | --- |
| Diagonal and curved walls | dd07, dd08, dd13 |
| Irregular, thick or free-form walls (caves, cliffs) | dd05, dd06 |
| Broken walls, many doorless gaps | dd12, dd05 |
| Objects that look like walls (shelves, counters, pews, fences, rails) | dd04, dd06, dd10, da02, da03, da05 |
| Many small rooms, thin interior walls, many doors | da04, da06 |
| Wide and double doors, gates, portcullis | dd07, dd09, da05 |
| Windows of every kind (glass line, barred, arrow slit) | dd07, da02, da03, da06 |
| Lights of all three tiers, wall-mounted and free-standing | all; large tier in dd07, dd09, da05 |
| Glow without a light (lava, crystals, magic circles) | dd06, dd08, da03 |
| Outdoor layouts | dd09, dd10 |
| Map size other than 25×25 | dd10 (30×20), dd11 (20×30) |
| A second art style (3D-rendered, real shadows) | da01–da06 |

Themes come in pairs (caves, outdoor, domestic, religious, fortified), so each kind of map is
likely to land in training even after the split takes about 15% of each dataset's layouts for
validation and 15% for test.

**Which tool:** Dungeondraft for what needs precise control (curves, caves, ruins, outdoor,
specific light placement); Dungeon Alchemist (DA) for furnished interiors, where its automatic
furnishing gives dense distractors and light sources for little work.

## Every layout must have

- **Size:** 25×25 squares unless the layout says otherwise. Dungeondraft: Roll20 grid preset (70 px
  per square). DA: 72 DPI (see "Dungeon Alchemist" below).
- **Fill the map:** walls come within 2–3 squares of the edge on at least two sides. No large
  empty margins: they only add easy background.
- **Walls:** at least 5 rooms or areas, with interior walls as well as outer walls.
- **Portals:** at least 5 doors, including 1 double door, and at least 2 windows wherever the
  theme has building walls.
- **Gaps:** at least 2 doorless openings (archway, doorless doorway or broken wall), each 1–3
  squares wide.
- **Lights:** at least 3 lit light sources covering at least 2 tiers, at least 1 of them
  wall-mounted (on the room side of the wall, not on it). In Dungeondraft each one is a sprite
  plus a light with range 8 (small), 12 (medium) or 16 (large). In DA the lights come with the
  light assets and are mapped to tiers afterwards.
- **Unlit fixtures:** at least 2 (unlit torch, cold brazier, empty fireplace) as negatives for
  the light class.
- **Distractors:** at least 10 objects, at least 3 of them **against or parallel to a wall**
  (shelf, counter, bed, bench, crates in a row). This is where the model learns "next to a wall
  is not a wall".
- **Shadows off** on every object in Dungeondraft (otherwise they become walls in
  `objects_line_of_sight`). DA exports no `objects_line_of_sight`.
- **Check** each export with `python -m data.rasterize` before making the next variant.

## The four variants

Every layout is exported four times. **Walls, portals, lights (position and `range`) and object
positions stay identical** in all four; only the look changes. Paint the variants in order and
re-export after each change. The table is written for Dungeondraft; for DA, use what it offers
for the same effect (room theme or materials for walls and floors, time of day for lighting), and
see the DA notes below.

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

### Export settings per variant

The settings that change between variants are grid and lighting. Everything else is the same
for all four exports of a layout.

**Same for every export:**

| Setting | Dungeondraft | Dungeon Alchemist |
| --- | --- | --- |
| Export type | Universal VTT (`.dd2vtt`) | Universal VTT (`.dd2vtt`) |
| Scale | Grid preset **Roll20** (70 px per square) | **72 DPI** (72 px per square) |
| Camera | Top-down (the only option) | **Orthographic (Top Down)** |
| Map size | The layout's size (25×25 by default), whole map, no crop | Same |
| Saved to | `data/raw/dungeondraft/ddNN_<v>.dd2vtt` | `data/raw/dungeon_alchemist/original/daNN_<v>.dd2vtt` |
| Embedded image | PNG, about 1–3 MB per file | JPEG, about 0.9 MB per file |

**What changes per variant:**

| Variant | Grid | Dungeondraft lighting | DA lighting | Scene before export |
| --- | --- | --- | --- | --- |
| `a` | **On** | **On**, daylight ambient | **Lights in the image**, daytime | The base map |
| `b` | **On** | **On**, same ambient as `a` | **Lights in the image**, same time as `a` | Walls restyled |
| `c` | **On** | **On**, **dark** ambient (night or dungeon) | **Lights in the image**, **night** | Busy floor |
| `d` | **Off** | **Off** (sprites only, no glow) | **Lights in VTT data only** | Third wall style, third floor |

**Check the .dd2vtt after each export** (`python -m data.rasterize` prints most of it):

| Check | Expected |
| --- | --- |
| `resolution.pixels_per_grid` | 70 (Dungeondraft) or 72 (DA) |
| `resolution.map_size` | The layout's size, identical in `a`–`d` |
| Embedded image size | `map_size` × `pixels_per_grid` px |
| `environment.baked_lighting` | Dungeondraft: `true` in `a`–`c`, `false` in `d`. DA: always `true` (not reliable) |
| Light count per tier (`lights small N, medium N, large N`) | Identical in `a`–`d`; after `retier_lights` for DA |
| Wall and portal counts | Identical in `a`–`d` |
| `objects_line_of_sight` | Empty in Dungeondraft (shadows off on every object); absent in DA |

### How to export, step by step

Dungeondraft is not installed where Claude can reach it, so its menu and field names here come
from its documentation and may be worded a little differently in the app. The DA names are the
ones from the `da01` pilot. If a name doesn't match, use the setting that does the same thing and
fix this page.

**Dungeondraft, one layout (`ddNN`):**

1. **Before the first export:** select every object and turn off its **shadow** (otherwise the
   object turns up in `objects_line_of_sight` as a wall). Check that every light is set to range
   8, 12 or 16.
2. **Variant `a`:** set the map up with the theme's walls and floor. In **Environmental
   Lighting**, choose a daylight ambient (light color, high opacity).
3. Open **File → Export**.
4. Set **Export type** to **Universal VTT**.
5. Pick the **Roll20** grid preset. The pixels per grid then reads **70**.
6. **Grid on, Lighting on** for `a`, `b` and `c`. For `d`: **Grid off, Lighting off**.
7. Export the whole map, with no region selected. Save as
   `data/raw/dungeondraft/ddNN_a.dd2vtt` (on Windows: the repo folder under
   `\\wsl$\Ubuntu\home\...\battlemap-walls\`).
8. **Variant `b`:** change only the wall style (or the wall color, if the theme has a single
   style). Repeat steps 3–7 and save as `ddNN_b.dd2vtt`.
9. **Variant `c`:** change the floor to a busy pattern. Set Environmental Lighting to a dark
   ambient (dark color, so the lights glow). Export as `ddNN_c.dd2vtt`.
10. **Variant `d`:** switch to the third wall style and third floor. Export with **Grid off and
    Lighting off**, as `ddNN_d.dd2vtt`.
11. Never move a wall, door, window, light or object between variants. Save the
    `.dungeondraft_map` after `a` (as `ddNN.dungeondraft_map`, kept outside `data/raw/`) so
    you can go back to it.

**Dungeon Alchemist, one layout (`daNN`):**

1. **Before the first export:** fill the map (the building should cover most of the 25×25
   squares). Don't move walls, doors or windows after the first export. Restyling or
   re-rolling furniture between variants is fine.
2. **Variant `a`:** set the room themes and materials. Set the time of day to **day**.
3. Open **Export** and choose **Universal VTT (.dd2vtt)**.
4. Set the camera to **Orthographic (Top Down)** and the resolution to **72 DPI**.
5. **Grid on** and lights **in the image** for `a`, `b` and `c`. For `d`: **Grid off** and lights
   **in VTT data only**.
6. Save as `data/raw/dungeon_alchemist/original/daNN_a.dd2vtt`.
7. **Variant `b`:** change the wall material only. Export as `daNN_b.dd2vtt` into `original/`.
8. **Variant `c`:** choose a busy floor material and set the time of day to **night**. Export as
   `daNN_c.dd2vtt`.
9. **Variant `d`:** pick a third wall and floor material. Export with **Grid off** and lights
   **in VTT data only**, as `daNN_d.dd2vtt`.
10. Convert the lights (writes the files the manifest reads):

    ```bash
    docker compose run --rm app python -m data.retier_lights --source dungeon_alchemist \
        data/raw/dungeon_alchemist/original/daNN_*.dd2vtt --out data/raw/dungeon_alchemist
    ```

    If it stops on an unknown light, add a rule for it in `data/configs/light_sources.toml` and
    run it again.

**After each layout (both tools):** check every variant, then rebuild the manifest:

```bash
docker compose run --rm app python -m data.rasterize data/raw/dungeondraft/ddNN_a.dd2vtt
docker compose run --rm app python -m data.manifest
```

In each preview, check the colors: red on the walls, magenta on the doors and windows, yellow
on the lit sources. The printed counts must match across `a`–`d` (the checks table above).
Then add the layout to [map-log.md](map-log.md).

The older exports `dd01`–`dd03` predate this table: only `dd01_a` was exported with lighting
off, so their `d` variants still have glow (they have no lights, so this changes little).

## Dungeondraft

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

- **Cave walls** (`dd05`): the rasterizer preview must show red along the cave walls. The format
  lists caves separately from walls, so make sure they end up in `line_of_sight`. If they don't,
  `data/rasterize.py` needs to read them too.
- **Curved walls** (`dd07`): the red band must follow the curve, not cut across it.
- **Light range** (`dd04_a`): **confirmed 21.10.** A light set to 8 is stored as `"range": 8`
  (grid squares), so `LIGHT_TIERS` stands. Lighting off in the export keeps the `lights` list.

**Assets to find in the Default pack** (Objects tool, pack name "Default"; about 1,500–1,800
objects). If one is missing, swap the item for one that exists rather than adding an asset pack:
third-party packs have their own licenses, and some limit use.

- Lights: wall torch, candle, candelabra, lantern (hanging and standing), brazier, campfire, fire
  pit, fireplace, forge.
- Distractors: bookshelf, bar counter, pew, pillar, mine-cart rail, crates, sarcophagus, tent,
  fence, rubble, crystal, magic circle.
- Portals: double door, portcullis or gate, barred door, barred window.

## Dungeon Alchemist

DA exports Universal VTT (.dd2vtt) with walls, portals and lights, so its maps fit the pipeline;
the only extra step is mapping its light ranges to the tiers. It adds:

- **Fast:** rooms are furnished automatically, so dense distractors and light sources cost little.
- **A second art style:** DA renders 3D-looking maps with real shadows. Many published maps look
  like this, so it helps on the hard test set, and it keeps the model from learning only
  Dungeondraft's look.

**Pilot `da01` (21.10): it works.** A furnished tavern, exported as `a` (grid, lights in the
image) and `d` (no grid, lights in VTT data only). Checked with an overlay of the labels on the
image:

- **Walls** sit on the drawn walls, diagonal walls included. DA writes each wall as straight
  2-point segments in `line_of_sight` and no `objects_line_of_sight`.
- **Portals** are right: doors are `closed: true`, windows `closed: false`, and every portal is
  1 square wide, so a **double door is two adjacent portals**. Both get the one portal class.
- **Lights** come from the light assets only, at the asset (sconces sit just inside the room,
  as the rules want). Each asset type has fixed `range` and `intensity` values; they don't match
  the tier ranges, so they are rewritten (below). The smoke effect has no light, correctly.
- **Variants:** `a` and `d` have identical walls, portals and light positions; only light colors
  differ. "VTT data only" really removes the glow from the image, although DA still writes
  `baked_lighting: true`, so that flag can't be trusted for DA files.
- **Format:** `format` 0.2, embedded **JPEG** image (the rasterizer reads it), 72 px per square
  at 72 DPI, about 0.9 MB per file.

**Export settings for every DA map:**

- Camera **Orthographic (Top Down)**, **72 DPI** (closest to 70; more DPI only makes files
  larger, since everything is resized to 70 px per square and training runs at 32).
- Grid and lights per the variant table above; `d` uses **lights in VTT data only**.
- Fill the map: the pilot's building covers about 16×13 of 25×25 squares, so walls are only 2.7%
  of pixels (Dungeondraft maps: about 5%). Size the map to the building, or add buildings.
- Variants may restyle and re-roll furniture, but **walls and portals must stay the same**.

**Converting the lights:** save exports to `data/raw/dungeon_alchemist/original/` (never edited),
then run

```bash
docker compose run --rm app python -m data.retier_lights --source dungeon_alchemist \
    data/raw/dungeon_alchemist/original/da02_*.dd2vtt --out data/raw/dungeon_alchemist
```

It matches each light's `range` and `intensity` to a rule in `data/configs/light_sources.toml`
(sconce and table candle: small; oven, cooking brazier and fireplace: medium), writes the tier's
range, and drops lights marked `drop`. A light asset that isn't in the config yet stops the run
with its values and position: find it in the image, decide its tier by the labeling rules, and
add a rule. Then check the converted file with `python -m data.rasterize` as usual.

**License:** DA's terms allow personal and limited commercial use of what you make and say
nothing about training models. The project trains on these maps and never redistributes them,
the same as Dungeondraft maps.

**Files:** DA maps go in `data/raw/dungeon_alchemist/` as `daNN_<variant>.dd2vtt`, a dataset of
their own with the same split rule by layout. The manifest reads only the top level of each
dataset folder, so `original/` is never picked up. DA's curved-wall support is not checked yet,
so layouts that need curves stay in Dungeondraft.

## The layouts

Light counts are lit sources per tier: S small (candle, torch, sconce), M medium (lantern,
brazier, campfire, fireplace), L large (bonfire, fire pit, forge). For DA layouts the counts are
a target for choosing room themes and assets, not exact.

### Week 2 · Dungeondraft: dd04–dd08

**dd04 · Tavern and inn** (wood). Ground floor of an inn: common room, kitchen, storeroom, 3–4
small guest rooms along a corridor.
- Portals: double front door, back door, a door per guest room, 4+ glass windows on outer walls.
- Gaps: open arch between common room and kitchen.
- Lights: S 4 (wall sconces, candles on tables), M 2 (fireplace, kitchen hearth). Unlit: 2
  sconces in the storeroom.
- Targets: **bar counter running parallel to a wall**, shelves behind it, benches along walls.
  The same theme as the DA pilot `da01`, in the other tool's style.

**dd05 · Natural cave** (cave walls, free-form tool). Winding cave system with 4–5 chambers and
narrow passages.
- Portals: one wooden door into a chamber walled off with masonry; otherwise none.
- Gaps: most passages are open (caves have gaps, not doors), 3+ of them.
- Lights: S 2 (torches on the cave wall, room side), M 2 (campfires). Unlit: a burnt-out campfire.
- Targets: **irregular thick walls**, boulders and stalagmites (not walls), an underground pool.

**dd06 · Mine** (cave walls plus carved stone). Mine tunnels with a timber-shored shaft, an
office and a storeroom.
- Portals: 3+ doors in the carved section, 1 double door (ore store).
- Gaps: 3+ open tunnel mouths.
- Lights: S 3 (wall torches), M 3 (hanging lanterns, a brazier). Unlit: 2 lanterns.
- Targets: **mine-cart rails** (long thin lines, not walls), timber beams, crates and ore piles,
  a glowing crystal vein (glow, not a light).

**dd07 · Castle keep** (thick stone). Keep with **round corner towers**, a courtyard, a
gatehouse and a great hall.
- Portals: **portcullis** and double gate in the gatehouse, 4+ doors, 4+ arrow slits (very thin
  windows).
- Gaps: open arches between courtyard and great hall.
- Lights: S 3 (wall torches), M 2 (braziers at the gate), L 1 (courtyard fire pit). Unlit: 2.
- Targets: **curved walls**, very thick walls, a courtyard (outdoor area inside walls), pillars
  in the great hall (background).

**dd08 · Wizard tower** (stone or brick). **Octagonal** main room, 45° corridors, round study,
laboratory.
- Portals: 4+ doors set in diagonal walls, 3+ windows in diagonal walls.
- Gaps: 2 doorless openings.
- Lights: S 3 (candles), M 2 (lanterns). Unlit: 1 lantern.
- Targets: **diagonal walls and portals at 45°**, glowing crystals and a glowing potion table
  (glow, not lights), shelves on diagonal walls.

### Week 3 · Dungeondraft: dd09–dd13

**dd09 · Fortified camp** (palisade, outdoor). Palisade ring with a gate, tents, a command
building, a corral.
- Portals: palisade gate (wide double), 2+ doors on the command building, 2 windows.
- Gaps: a breach in the palisade, 2 squares wide.
- Lights: S 3 (torches on poles, free-standing), M 3 (campfires), L 1 (central bonfire).
  Unlit: a cold fire pit.
- Targets: **palisade as wall**, **fences around the corral (not walls)**, tents (background),
  trees, carts.

**dd10 · Village street** (wood and plaster, outdoor), **30×20 squares**. A street with 4–5
small houses and shops on both sides.
- Portals: a door per house (one double, for a shop), 6+ windows.
- Gaps: an open shop front (counter, no wall), a doorless shed.
- Lights: M 4 (street lanterns on posts), S 2 (lanterns by doors, as wall lights). Unlit: 1
  street lantern.
- Targets: **garden fences and low walls** (not walls), a well, market stalls, a non-square map.

**dd11 · Sewer** (brick), **20×30 squares**. Sewer channels with walkways, a cistern, a
smugglers' room.
- Portals: 3+ doors, 2 iron gates (doors), 2 barred grates in walls (windows).
- Gaps: 3+ open channel junctions.
- Lights: S 3 (wall torches), M 1 (smugglers' lantern). Unlit: 2. Dark ambient in every variant
  except `d`.
- Targets: **water channels next to walls** (the water is not a wall), walkway edges, narrow
  corridors, a non-square map.

**dd12 · Ruins** (broken stone, partly outdoor). Ruined abbey: half-standing walls, rubble,
overgrowth.
- Portals: 2 surviving doors, 2 windows.
- Gaps: **5+ breaches and broken wall ends**; walls end at the broken edge, the rubble is not a
  wall.
- Lights: M 2 (campfires), S 1 (torch on a standing wall). Unlit: 1.
- Targets: **gaps that must stay gaps**, rubble, trees growing in rooms, vines over walls.

**dd13 · Crypt** (stone). Catacombs: corridors with burial alcoves, a round central chamber,
an ossuary.
- Portals: 3+ doors, 1 double door to the central chamber.
- Gaps: 3+ alcove openings (open niches in the wall, which are gaps).
- Lights: S 4 (candles in alcoves), M 2 (braziers). Unlit: 3 candles.
- Targets: **wall niches** (the wall bends around them), **sarcophagi in rows**, a **round
  chamber** (curved walls).

### Week 4 · Dungeon Alchemist: da02–da06

Made at the start of week 4, before the stage 2 run. Each needs the light conversion step; a new
light asset type stops it until a rule is added.

**da02 · Manor library and study.** Library hall, reading room, study, a narrow gallery.
- Portals: double door into the library, 3+ doors, 6+ windows.
- Gaps: two doorless openings between library bays.
- Lights: S 4 (candelabras, desk candles), M 2 (fireplace, standing lantern).
- Targets: **bookshelves lining the walls and in free-standing rows**, the hardest "looks like a
  wall" case. Rugs with straight borders.

**da03 · Temple.** Nave with side aisles, sanctum, vestry.
- Portals: large double door, 3+ doors, 4+ windows.
- Gaps: arches between nave and aisles.
- Lights: S 5 (candles), M 2 (braziers).
- Targets: **rows of pews** (parallel lines), **rows of pillars** (background), a glowing magic
  effect if DA has one (glow, not a light: add it as a `drop` rule).

**da04 · Prison.** Cell block of 6–8 small cells, guard room, interrogation room.
- Portals: a door on every cell, 3+ doors, 2 windows.
- Gaps: one open corridor junction.
- Lights: S 4 (wall torches in the corridor), M 1 (guard room brazier).
- Targets: **many small rooms and many doors**, thin walls, beds against walls. Cell fronts are
  walls with a door, not rows of bars.

**da05 · Smithy and warehouse.** Forge, workshop, warehouse, yard.
- Portals: **wide double doors**, 3+ doors, 3+ windows.
- Gaps: an open side of the forge onto the yard.
- Lights: L 1 (forge), M 2 (braziers), S 2 (wall lanterns).
- Targets: **rows of crates** and racks (wall-like lines), workbenches against walls.

**da06 · Townhouse.** A dense two-wing house with 10+ small rooms.
- Portals: **10+ doors**, 1 double door, 6+ windows.
- Gaps: 2 open arches.
- Lights: S 5 (candles, wall sconces), M 2 (fireplaces).
- Targets: **thin walls close together**, beds, wardrobes and dressers against walls, rugs.

## Edge cases decided for this set (21.10)

These are also in the edge cases log in [labeling-rules.md](labeling-rules.md).

| Case | Decision | Needed for |
| --- | --- | --- |
| Pillars and columns | Background, like statues. A pillar class stays a stretch goal | dd07, da03 |
| Tents | Background: they are objects, not built walls | dd09 |
| Rows of cell bars | Avoid: draw cell fronts as walls with a barred door portal | da04 |
| Open shop front with a counter | Gap (background); the counter is furniture | dd10 |
| Arrow slits | Portal (a very thin window) | dd07 |

## Time

- **Dungeondraft:** about 25–30 minutes per layout plus 10 minutes for the three restyles and four
  exports, so about 40 minutes per layout: 3.5 hours each in weeks 2 and 3.
- **DA:** faster to furnish; with the four exports and the light conversion, plan about 30
  minutes per layout: 2.5 hours at the start of week 4.

If time runs short, drop layouts from the end of each week's list, but keep at least one of each
pair (caves, outdoor, domestic, religious, fortified).
