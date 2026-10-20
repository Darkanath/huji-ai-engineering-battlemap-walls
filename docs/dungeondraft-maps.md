# Dungeondraft maps

The maps in `data/raw/dungeondraft/` (gitignored), named `<layout>_<variant>.dd2vtt` as set in
[labeling-rules.md](labeling-rules.md). All style variants of one layout always go in the same
split. All are 25×25 squares at 70 px per square.

This log keeps what the file names leave out, for the data summary and the error analysis. The
manifest CSV (week 2) will take it over.

| File | Layout | Variant | Walls | Objects | Wall / portal share | Notes |
| --- | --- | --- | --- | --- | --- | --- |
| `demo-training-map` | demo | - | stone | none | 7.4% / 0.6% | Test fixture; keeps its name because the tests use it |
| `dd01_a` | dd01 | a | wood | few | 4.8% / 0.3% | Buildings on dirt; bathtub, stove, bushes. 3 portals stacked at (5, 20.5) |
| `dd01_b` | dd01 | b | other wall style, other floor | few | 4.8% / 0.3% | One door 1 px off from `a` (142 mask pixels); same stacked portals as `a` |
| `dd01_c` | dd01 | c | other wall style, grey patterned floor | few | 4.8% / 0.3% | Same stacked portals as `a` |
| `dd02_a` | dd02 | a | wood | many | 5.1% / 0.2% | River across the top; books, rugs, cobwebs as distractors |
| `dd02_b` | dd02 | b | other wall style | many | 5.1% / 0.2% | Floor, lighting and grid as `a` |
| `dd02_c` | dd02 | c | other wall style, grey patterned floor | many | 5.1% / 0.2% | Lighting and grid as `a` |
| `dd03_a` | dd03 | a | stone | none | 5.4% / 1.1% | Many windows (23 portals) |
| `dd03_b` | dd03 | b | other wall style | none | 5.4% / 1.1% | Floor, lighting and grid as `a` |
| `dd03_c` | dd03 | c | other wall style, grey patterned floor | none | 5.4% / 1.1% | Lighting and grid as `a` |
| `dd01_d` | dd01 | d | thin dark walls, parquet floor, **no grid** | few | 4.8% / 0.3% | Parquet forms a square pattern: a hard case for grid detection. Same stacked portals as `a` |
| `dd02_d` | dd02 | d | thin dark walls, grey concrete floor, **no grid** | many | 5.1% / 0.2% | |
| `dd03_d` | dd03 | d | thin dark walls, wooden plank floor, **no grid** | none | 5.4% / 1.1% | Glass windows are thin lines in the wall, as in `a` |

All `b`, `c` and `d` variants have the same walls and portals as their `a` (masks identical, except the
1 px door in `dd01_b`). Share of pixels that change away from the walls, compared with `a`:
`dd01_b` 23%, `dd02_b` 3%, `dd03_b` 2% (wall style only); every `c` 27–32% (new floor); `d` 13–36%
(new floor, no grid). The `c` variants share one grey patterned floor; the `d` variants each
have their own floor and no grid.

For the next layouts: 4 variants (`a`–`d`) as in the labeling rules, with different floors across
layouts and the grid off in at least one variant.
