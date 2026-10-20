# Dungeondraft maps

The maps in `data/raw/dungeondraft/` (gitignored), named `<layout>_<variant>.dd2vtt` as set in
[labeling-rules.md](labeling-rules.md). The 3 style variants of one layout always go in the same
split. All are 25×25 squares at 70 px per square.

This log keeps what the file names leave out, for the data summary and the error analysis. The
manifest CSV (week 2) will take it over.

| File | Layout | Variant | Walls | Objects | Wall / portal share | Notes |
| --- | --- | --- | --- | --- | --- | --- |
| `demo-training-map` | demo | - | stone | none | 7.4% / 0.6% | Test fixture; keeps its name because the tests use it |
| `dd01_a` | dd01 | a | wood | few | 4.8% / 0.3% | Buildings on dirt; bathtub, stove, bushes. 3 portals stacked at (5, 20.5) |
| `dd01_b` | dd01 | b | other wall style, other floor | few | 4.8% / 0.3% | One door 1 px off from `a` (142 mask pixels); same stacked portals as `a` |
| `dd01_c` | dd01 | c | other wall style, same floor as `b` | few | 4.8% / 0.3% | Only 1 portal at (5, 20.5); mask identical to `a` |
| `dd02_a` | dd02 | a | wood | many | 5.1% / 0.2% | River across the top; books, rugs, cobwebs as distractors |
| `dd02_b` | dd02 | b | other wall style | many | 5.1% / 0.2% | Floor, lighting and grid as `a` |
| `dd02_c` | dd02 | c | other wall style | many | 5.1% / 0.2% | Floor, lighting and grid as `a` |
| `dd03_a` | dd03 | a | stone | none | 5.4% / 1.1% | Many windows (23 portals) |
| `dd03_b` | dd03 | b | other wall style | none | 5.4% / 1.1% | Floor, lighting and grid as `a` |
| `dd03_c` | dd03 | c | other wall style | none | 5.4% / 1.1% | Floor, lighting and grid as `a` |

All `b` and `c` variants have the same walls and portals as their `a` (masks identical, except the
1 px door in `dd01_b`). Away from the walls the images differ little: 23% of pixels change in
`dd01`, about 2–3% in `dd02` and `dd03`. Every variant has the grid on.

For the next layouts: make the variants differ in more than the wall style. Change the floor
texture, and turn the grid or lighting off in at least one variant. Week 6's grid detection needs
some maps exported without a grid.
