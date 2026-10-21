# Dungeondraft maps

The maps in `data/raw/dungeondraft/` (gitignored), named `<layout>_<variant>.dd2vtt` as set in
[labeling-rules.md](labeling-rules.md). All style variants of one layout always go in the same
split. All are 25×25 squares at 70 px per square.

This log keeps what the file names leave out, for the data summary and the error analysis. The
manifest CSV (week 2) will take it over.

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

All `b`, `c` and `d` variants have the same walls and portals as their `a` (masks identical, except the
1 px door in `dd01_b`). Share of pixels that change away from the walls, compared with `a`:
`dd01_b` 23%, `dd02_b` 3%, `dd03_b` 2% (wall style only); every `c` 27–32% (new floor); `d` 13–36%
(new floor, no grid). The `c` variants share one grey patterned floor; the `d` variants each
have their own floor and no grid.

**Lights (21.10):** none of these exports has lights (`lights` is empty in every file), and none
draws a lit light source (`dd01` has an unlit stove), so the empty list is the correct label. They
stay as they are, as lights-free maps. From `dd04` on, the Lights column gives the count per tier
(small / medium / large).

The next layouts, `dd04`–`dd18`, follow [map-specs.md](map-specs.md): what goes on each layout
and what changes in each variant.
