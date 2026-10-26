# Labeling rules

These rules define what the model learns. They apply to every dataset: synthetic maps, Dungeondraft
maps, Dungeon Alchemist maps and the hand-traced test set. If a map breaks a rule, fix the map,
not the rule. If a rule turns out to be wrong, change it here first, then regenerate the affected
masks.

## Classes

| Id | Class | Meaning |
| --- | --- | --- |
| 0 | background | Everything else: floor, terrain, furniture, open gaps, unlit light fixtures |
| 1 | wall | Blocks both sight and movement |
| 2 | portal | A door or window set in a wall |
| 3 | light | A lit light source drawn in the image |

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

## Light (class 3)

A light is a **lit light source drawn in the image**: you can see the flame or the lamp.

There is one light class. How bright a light is cannot be read from the image (the same torch
sprite could be 20 ft or 40 ft of light), so each light gets a **size tier** instead, and the
brightness comes from a fixed table. The GM can change the values in the app before download.

| Tier | Examples | Label disc radius | Bright / dim (squares) | `range` in the .dd2vtt |
| --- | --- | --- | --- | --- |
| small | candle, candelabra, torch, wall sconce | 0.25 squares | 4 / 4 (torch: 20 ft + 20 ft) | 8 |
| medium | lantern, brazier, campfire, lit fireplace | 0.40 squares | 6 / 6 (lantern: 30 ft + 30 ft) | 12 |
| large | bonfire, large fire pit, forge | 0.60 squares | 8 / 8 (project choice) | 16 |

- The bright and dim values follow D&D 5e where it has one (torch, lantern); the large tier is a
  project choice. The label side (tier `range` and disc radius) is `LIGHT_TIERS` in
  `data/rasterize.py`; the output side (bright, dim, `range`, `intensity` written to the .dd2vtt,
  editable in the app) will be `postprocess/configs/lights.toml`. This page and both must agree.
- **Roll20 check (21.10, `dd04_a`):** the export imports into Roll20 with every light in place,
  and `range` is in grid squares, so the `range` column stands. The exact bright and dim radius
  Roll20 makes from `range` and `intensity` was not measured; check it on the writer's output in
  week 5 and adjust `postprocess/configs/lights.toml` if needed.
- **Tier comes from `range`.** When you place a light in Dungeondraft, set its range to the
  tier's value in the last column. The rasterizer reads the tier back from `range` and stops with
  an error on a range that matches no tier, so a light placed with the default range is caught.
  Dungeon Alchemist sets ranges itself, so its lights are mapped to tiers by
  `data/retier_lights.py` before the rasterizer sees them (see "Making Dungeon Alchemist maps").
- **Position:** the center of the flame or lamp. A **wall-mounted** light (torch, sconce) goes on
  the room side of the wall, just off it, never on the wall's centerline. On the centerline its
  disc would be split by the wall band into two blobs, and Roll20 could not tell which side it
  lights.
- Color, intensity and shadows are not labeled. Leave Dungeondraft's defaults.

**Not lights:**

- Unlit torches, empty braziers, cold fireplaces.
- Glow with no drawn source: ambient lighting, colored tints, light pools from off-map sources.
- Lava, glowing water, magic circles, crystals and other things that glow but are not a lamp or
  a fire. They go in the edge cases log if a map needs a decision.
- Windows letting in daylight: they are portals, not lights.

## How labels are drawn

Labels come **only** from `.dd2vtt` files (`data/rasterize.py`). Never use `.dungeondraft_map`
source files.

- Walls are `line_of_sight` plus `objects_line_of_sight` polylines, drawn as a band **0.25
  squares** wide along the centerline.
- Portals are their `bounds` segment, drawn **0.30 squares** wide, on top of the walls. This way a
  portal always wins over the wall it sits in.
- Lights are a filled disc at `position`, with the radius of their tier (0.25, 0.40 or 0.60
  squares), drawn **first**, so walls and portals are drawn over them. A wall must never get a
  gap from a torch next to it; losing part of a small light's disc is harmless.
- Draw order: lights, then walls, then portals.
- **Label width is fixed, whatever the drawn wall width.** A .dd2vtt only stores centerlines, and
  post-processing skeletonizes the mask back to centerlines anyway. A consistent band is an easier
  target than one that changes with the art style. The images still have to show many wall
  widths, so the synthetic generator varies them.
- Masks are stored as **PNG** (exact class ids). Images are stored as JPEG.

## Making Dungeondraft maps

What goes on each new layout and how its variants differ is in [map-specs.md](map-specs.md).

- **Map size:** 25×25 squares unless the layout needs otherwise.
- **Export:** Universal VTT with the **Roll20 grid preset** (70 px per square).
- **Style variants:** export each layout **4 times** (`a`–`d`) with the same walls and portals
  and different art: wall styles, floor textures (different floors across layouts too), lighting.
  At least one variant has the **grid off**. Name them `<layout>_<variant>.dd2vtt`, for example
  `dd01_a.dd2vtt` ... `dd01_d.dd2vtt`. All variants of one layout always go in the same split.
- **Content:** walls, doors, windows, at least one doorless opening, and a scatter of furniture as
  distractors. No detailing needed.
- **Lights:** at least 3 lit light sources per layout, covering at least two tiers (for example
  wall torches plus a brazier or a campfire). Place the sprite, then a Dungeondraft light on it
  with the tier's `range` (see "Light (class 3)"). A light object with no drawn sprite is not
  allowed: the model can only learn what it can see. Add a few unlit fixtures too, as
  distractors. Lights are the same in all variants of a layout.
- **Light glow:** if the export draws Dungeondraft's light glow into the image, vary the lighting
  across variants, so the model learns the sprite and not only the glow (third-party maps often
  have no glow).
- **Shadows:** do not turn on shadow casting for furniture or other objects. Dungeondraft exports
  shadow-casting objects to `objects_line_of_sight`, which the rasterizer labels as walls, so a
  shadow-casting table would become a wall in the mask.
- **Check every export:** run `python -m data.rasterize <map>.dd2vtt` and look at the
  `_preview.jpg`. Red must cover only walls, magenta only doors and windows, and the light discs
  only lit light sources, at the right tier size.

## Making Dungeon Alchemist maps

Dungeon Alchemist (DA) furnishes rooms automatically and renders a 3D-looking style, so its maps
add a second art style to the real data. Its exports were checked on the pilot `da01` (details
in [map-specs.md](map-specs.md)).

- **Export:** Universal VTT, camera **Orthographic (Top Down)**, **72 DPI** (72 px per square;
  the rasterizer resizes to 70). Variant `d` exports lights to the **VTT data only**, so the
  image has no glow. DA writes `baked_lighting: true` either way; ignore that flag.
- **Variants and names:** as for Dungeondraft, 4 variants `daNN_a` ... `daNN_d` with the same
  walls and portals. A restyle may re-roll furniture and lights; that is fine, because every
  export carries its own labels.
- **Doors and windows:** DA writes portals 1 square wide, so a double door is two portals side by
  side. Doors are `closed: true`, windows `closed: false`; both are the portal class.
- **Lights:** come from DA's light assets, with ranges DA chooses. Save every export to
  `data/raw/dungeon_alchemist/original/` and convert it with `python -m data.retier_lights
  --source dungeon_alchemist ... --out data/raw/dungeon_alchemist`. The rules in
  `data/configs/light_sources.toml` map each asset's `range` and `intensity` to a tier, or drop
  it (glowing crystals, magic effects). A light with no rule stops the conversion: find it in
  the image, decide its tier by the rules above, and add a rule. Never edit the originals.
- **Check every export** with the rasterizer preview, as for Dungeondraft maps.

## Hand-tracing the test set

Test maps are third-party or hand-made images with no .dd2vtt, so their labels are traced by hand
and saved as .dd2vtt. The same rules apply:

- Trace each wall along its **centerline**, as one polyline per continuous run of wall.
- End the wall at each side of a doorless opening, so the gap stays open.
- Place each door or window as a portal across the wall, with its `bounds` from jamb to jamb.
- Place a light on each lit light source, with its tier's `range`, as for Dungeondraft maps.
- Check the trace with the rasterizer preview, the same way as Dungeondraft maps.
- Published third-party maps stay in the test set only and are never redistributed.

**Tool: Dungeondraft**, tracing over the image, then swapping the original image into the export.

1. **Prepare the image.** Crop it to a whole number of squares, with the grid starting at the
   top-left corner. Save it as `data/raw/test/tNN.jpg` (or `.png`/`.webp`).
2. **Record it** in `data/raw/test/test_maps.csv`: file, squares across and down, source and
   license, and set (`in-domain` or `hard`).
3. **Set up Dungeondraft.** New map with the same size in squares. Load the image as the trace
   overlay and scale it so one image square equals one Dungeondraft square, corners aligned.
4. **Trace.** Walls with the wall tool along the drawn walls' centerlines, ending at each side of
   a doorless opening. Doors and windows as portals in those walls. Use the cave or free-form
   tools for cliffs and cave walls. Lights on the lit light sources, with the tier's range. No
   objects, no shadows.
5. **Export** Universal VTT as `tNN.dd2vtt`. Its embedded image is Dungeondraft's rendering,
   not the test image.
6. **Swap the image:** `python -m data.attach_image data/raw/test/tNN.dd2vtt data/raw/test/tNN.jpg`
   embeds the original image and sets `pixels_per_grid` from its size. It refuses an image whose
   size isn't `map_size` × a whole px per square.
7. **Check:** `python -m data.rasterize data/raw/test/tNN.dd2vtt`. In the preview, red must sit
   on the drawn walls of the original image, magenta on its doors and windows, and the light
   discs on its lit light sources. If everything is shifted the same way, the overlay was
   misaligned in step 3.

## Edge cases log

When a map raises a case these rules don't cover, decide it, add it here with the map name, and
apply it everywhere.

| Case | Decision | Example map |
| --- | --- | --- |
| Door flagged `freestanding` but sitting in a wall | Portal | `demo-training-map` |
| Glass window drawn as a thin plain line in the wall | Portal; subtle but visible | `dd03` (right-hand room) |
| Several portals stacked at the same position | One portal; the mask is the same either way. Deduplicate before counting portals or writing a .dd2vtt | `dd01_a`, `dd01_b` |
| Several lights stacked on one sprite | One light, with the largest tier. Deduplicate (within 0.25 squares) before drawing | - |
| Pillars and columns | Background, like statues. A pillar class stays a stretch goal | `dd07`, `da03` (planned) |
| Tents | Background: objects, not built walls | `dd09` (planned) |
| Rows of cell bars | Avoided in maps: cell fronts are walls with a barred door portal | `da04` (planned) |
| Open shop front with a counter | Gap (background); the counter is furniture | `dd10` (planned) |
| Arrow slits | Portal: a very thin window | `dd07` (planned) |
| Double door written as two portals (DA) | Two portals; the mask is one continuous portal band either way | `da01` |
| Light with no drawn source (DA effect) | Dropped by a `drop` rule in `light_sources.toml` | - |
