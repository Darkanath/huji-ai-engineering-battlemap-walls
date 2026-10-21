# huji-ai-engineering-battlemap-walls

Course project for AI Engineering (Hebrew University). Upload a top-down battlemap image and get
back a Universal VTT file (`.dd2vtt`) with **walls**, **portals** (doors and windows) and **light
sources** already placed, ready to upload to Roll20 for dynamic lighting and fog of war.

The core is a semantic segmentation model (U-Net with a pretrained ResNet-18 encoder, PyTorch)
that labels every pixel as background, wall, portal or light. A post-processing pipeline then
turns the mask into wall polylines, portal segments and lights. Each light's brightness comes from
its size tier (small: torch, medium: brazier, large: bonfire) and an editable lookup table, since
an image does not show how far a light reaches.

- Input: `.png`, `.jpg`/`.jpeg` or `.webp` image
- Output: `.dd2vtt` (walls, portals, lights, embedded map image), at 70 px per grid square
- Runs on CPU, under Docker

See [`docs/PLAN.md`](docs/PLAN.md) for the full plan, data strategy and evaluation.
Week-by-week tasks are in [`docs/roadmap/`](docs/roadmap/README.md).

## Status

Week 1 of 9 (final presentation 2026-12-23).

- [x] Repo layout, Docker setup
- [x] `.dd2vtt` -> class mask rasterizer, with tests
- [ ] Synthetic map generator, Canny baseline, evaluation harness
- [ ] U-Net training (synthetic, then fine-tuning on the real maps)
- [x] Light labels in the rasterizer
- [x] Dungeon Alchemist pilot (`da01`) and its light conversion (`data/retier_lights.py`)
- [ ] Real maps: Dungeondraft `dd04`–`dd13`, Dungeon Alchemist `da02`–`da06` (`docs/map-specs.md`)
- [ ] Mask -> `.dd2vtt` post-processing and writer
- [ ] Light post-processing (blob -> position and size tier -> range)
- [ ] Gradio app

## Quick start

Requires Docker with Docker Compose. On Windows, enable WSL integration in Docker Desktop.

```bash
docker compose build                    # Ubuntu 24.04, Python 3.12, CPU-only PyTorch
docker compose run --rm app pytest      # run the tests
docker compose run --rm app ruff check  # lint
```

Rasterize a `.dd2vtt` into a training pair (JPEG image, PNG class mask, JPEG preview overlay):

```bash
docker compose run --rm app python -m data.rasterize \
    data/raw/dungeondraft/demo-training-map.dd2vtt --out data/processed/demo
```

Mask classes: `0` background, `1` wall, `2` portal, `3` light. Masks are always PNG so class ids
stay exact.

Dungeon Alchemist exports set light ranges per asset, not by tier. Map them to the tiers first
(the originals in `original/` are never changed):

```bash
docker compose run --rm app python -m data.retier_lights --source dungeon_alchemist \
    data/raw/dungeon_alchemist/original/da01_a.dd2vtt --out data/raw/dungeon_alchemist
```

## Repo layout

```
data/            rasterize.py (.dd2vtt -> mask), retier_lights.py (other tools' lights -> tiers),
                 configs/; later the synthetic generator and manifests
  raw/           source .dd2vtt files: dungeondraft/, dungeon_alchemist/, synthetic/, test/
                 (gitignored, except the demo map used by the tests)
  processed/     image + mask pairs, manifest.csv (gitignored)
train/           dataset, augmentations, training loop, configs/
eval/            metrics (pixel IoU, boundary F1, visibility IoU), Canny baseline, reports
postprocess/     mask -> polylines -> portals -> lights -> .dd2vtt writer
app/             Gradio app (upload, overlay preview, download .dd2vtt)
notebooks/       exploration and figures for the presentation
docs/            PLAN.md, labeling-rules.md, training.md, map-specs.md, map-log.md, roadmap/
runs/            checkpoints and MLflow logs (gitignored)
tests/           pytest
```

`data/` and `runs/` are mounted into the container, so datasets, checkpoints and logs stay on the
host.

## Data and licensing

Training data is synthetic maps and real maps made for this project in Dungeondraft and Dungeon
Alchemist. Labels come only from `.dd2vtt` exports. Published third-party maps are used only in
the test set and are never redistributed.

## License

MIT, once the course is done.
