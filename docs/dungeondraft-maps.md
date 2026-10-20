# Dungeondraft maps

The maps in `data/raw/dungeondraft/` (gitignored), named `<layout>_<variant>.dd2vtt` as set in
[labeling-rules.md](labeling-rules.md). The 3 style variants of one layout always go in the same
split. All are 25×25 squares at 70 px per square.

This log keeps what the file names leave out, for the data summary and the error analysis. The
manifest CSV (week 2) will take it over.

| File | Layout | Variant | Walls | Objects | Wall / portal share | Notes |
| --- | --- | --- | --- | --- | --- | --- |
| `demo-training-map` | demo | - | stone | none | 7.4% / 0.6% | Test fixture; keeps its name because the tests use it |
| `dd01_a` | dd01 | a | wood | few | 4.8% / 0.3% | Buildings on dirt; bathtub, stove, bushes |
| `dd02_a` | dd02 | a | wood | many | 5.1% / 0.2% | River across the top; books, rugs, cobwebs as distractors |
| `dd03_a` | dd03 | a | stone | none | 5.4% / 1.1% | Many windows (23 portals) |

Still to do: variants `b` and `c` of each layout (different wall style, floor texture, lighting or
grid).
