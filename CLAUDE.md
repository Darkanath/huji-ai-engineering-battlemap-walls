# Battlemap Auto-Walling

Course project (Hebrew University, AI Engineering). Upload a top-down battlemap image and get back a
Universal VTT file (.dd2vtt) with walls, portals and light sources placed, ready to upload to
Roll20 for dynamic lighting and fog of war. The core is a semantic segmentation model (U-Net)
trained in PyTorch.

Full plan: `docs/PLAN.md`. Read it before starting a new piece of work. Final presentation: 2026-12-23.
Week-by-week tasks, file names and done criteria: `docs/roadmap/week-NN.md` (index in
`docs/roadmap/README.md`). Work from the current week's file and tick its boxes as tasks finish.

## Hard constraints (do not drift from these)

- **Python only.** All code is Python. The only non-Python files allowed are the Dockerfile,
  docker-compose.yml, pyproject/requirements, config files (YAML/TOML) and docs. No JavaScript or
  hand-written HTML; the UI is built with Gradio.
- **Images in.** Inference input is an image only: `.png`, `.jpg`/`.jpeg`, `.webp`.
- **Labels come only from .dd2vtt files.** Never read or depend on `.dungeondraft_map` source files.
- **4 classes:** `0 = background`, `1 = wall`, `2 = portal` (doors and windows together; no
  door/window split, not even as a stretch goal), `3 = light` (a drawn light source: torch,
  candle, lantern, brazier, campfire, bonfire). One light class only; brightness comes from the
  blob's **size tier** (small / medium / large) and a lookup table, never from a learned
  regression. Lights are lower priority than walls and portals: if time runs short, they are cut
  first.
- **CPU only.** Intel CPU, no NVIDIA GPU. Install the CPU-only PyTorch build. Never add CUDA
  dependencies or `.cuda()` calls. Use `torch.device("xpu")` only if `torch.xpu.is_available()`,
  otherwise CPU.
- **Runs on the laptop under Docker**, Ubuntu 24.04 base image, started with Docker Compose.
- **Every dataset is saved to disk** (never generated on the fly during training) so it can be
  showcased: image, .dd2vtt and mask per map, a fixed seed per map, and a manifest CSV.
- **Pretrained models are allowed.** Default model: U-Net with a pretrained ResNet-18 encoder
  (`segmentation_models_pytorch`).
- Solo project. Keep the scope at what one person can finish by 2026-12-23.

## Stack

- Python 3.12 (Ubuntu 24.04 default), in a virtual environment inside the container (PEP 668).
- PyTorch + torchvision CPU wheels: `pip install torch torchvision --index-url https://download.pytorch.org/whl/cpu`
- `segmentation_models_pytorch`, `albumentations`, `opencv-python-headless`, `scikit-image`,
  `numpy`, `Pillow`, `shapely` (visibility polygons), `onnxruntime` (serving), `gradio` (UI),
  `fastapi` + `uvicorn` (optional API), `mlflow` (run tracking), `pytest`, `ruff`.

## Repo layout

```
data/            generator.py (synthetic maps), rasterize.py (.dd2vtt -> mask), manifest tools
  raw/           source .dd2vtt files (dungeondraft/, synthetic/, test/)   [gitignored]
  processed/     image + mask pairs, manifest.csv                          [gitignored]
train/           dataset, augmentations, training loop, configs/
eval/            metrics (pixel IoU, boundary F1, visibility IoU), baseline (Canny), reports
postprocess/     mask -> polylines -> portals -> .dd2vtt writer
app/             Gradio app (upload, overlay preview, download .dd2vtt)
notebooks/       exploration and figures for the presentation
docs/            PLAN.md, labeling rules, results
runs/            checkpoints and MLflow logs                               [gitignored]
tests/           pytest
```

Datasets, checkpoints and logs are mounted as Docker volumes so they persist on the host.

## Universal VTT (.dd2vtt) facts

- One JSON file. All coordinates are in **grid squares**, not pixels.
- `resolution.pixels_per_grid`, `resolution.map_origin`, `resolution.map_size`. Use **70 px per
  square**, Roll20's default: export Dungeondraft maps with the Roll20 grid preset (much smaller
  files than Dungeondraft's default 256), and write the output .dd2vtt image at 70 px per square so
  Roll20 places it at native scale. Code must still read any `pixels_per_grid` value.
- `line_of_sight`: list of polylines (lists of `{x, y}`); these are the walls.
- `objects_line_of_sight`: extra sight blockers; treat as walls.
- `portals`: each has `position`, `bounds` (2 endpoints), `rotation`, `closed`, `freestanding`.
  No door/window type.
- `lights`: each has `position`, `range` (grid squares), `intensity`, `color`, `shadows`. Labels
  read `position` and map `range` to a size tier; the output writes one light per detected blob,
  with `range` and `intensity` from the tier table (`postprocess/configs/lights.toml`).
- `image`: base64-encoded PNG of the map. **This embedded image is the source of truth** for
  training. A same-named `.png` next to a `.dd2vtt` in `data/raw/` is optional: use it only for
  viewing, and if code reads it, first check its size matches `map_size` x `pixels_per_grid`.
- Roll20 accepts .dd2vtt directly via Page Menu -> Upload Background.

## Pipeline conventions

- **Default map size: 25x25 squares** (1750x1750 px at 70 px per square). The synthetic generator
  and new Dungeondraft maps use it by default, and the app pre-fills it as the map size the user
  can change. Code must still accept any map size.

- **Scale normalization:** datasets are stored at 70 px per square; training and inference run at
  **32 px per square** (walls about 8 px thick). Inference rescales the upload using the detected
  grid, or a user-entered map width in squares as fallback.
- **Storage formats:** map images and previews are saved as JPEG (quality 90; the demo map is
  0.63 MB vs 1.68 MB as PNG). Masks are **always PNG**: JPEG is lossy and would corrupt class ids.
- Training: random 256x256 crops, ~2,000 crops per epoch, cross-entropy + Dice with class weights
  computed from the training split's pixel shares (wall share varies with wall thickness; demo
  map: walls 7.4%, portals 0.6%). Stage 1 synthetic, stage 2 fine-tune on Dungeondraft.
- Splits are **by map, never by crop**; all style exports of one Dungeondraft layout (`dd01_a`..`dd01_d`)
  stay in the same split. The test set is run once, at the end.
- Post-processing: close small gaps with a kernel well under 0.25 square (doorless openings must
  stay open), skeletonize, trace, Douglas-Peucker, cut walls where portals cross, convert to grid
  units, write .dd2vtt.
- Labeling rules: wall = blocks sight and movement (building walls, palisades, cave walls,
  cliffs). Portal = door or window in a wall. An open gap with no door is just a gap. Furniture,
  counters, rugs, trees, boulders and water are not walls. Light = a lit light source drawn in the
  image; its tier is set by its `range` in the .dd2vtt (see `docs/labeling-rules.md`).
- Lights in the mask: a disc at the light's `position`, radius by tier (0.25 / 0.40 / 0.60
  squares), drawn **under** walls and portals so a wall-mounted torch never cuts a gap in a wall.
  Post-processing: light blob -> centroid (position) + area (tier) -> range from the tier table.
- Data licensing: train only on synthetic maps and maps the user made. Published third-party maps
  go in the test set only and are never redistributed.

## Working conventions

- Type hints, small functions, docstrings on public functions. Format and lint with `ruff`.
- Every module that transforms data gets a pytest test, using the demo map in `data/raw/dungeondraft/`.
- Seed everything (`random`, `numpy`, `torch`) from config; log every run to MLflow with its config.
- Run everything through Docker Compose, e.g. `docker compose run --rm app pytest`.
- Set `torch.set_num_threads()` to the physical core count; use channels-last memory format.
- Prefer simple, working, measured solutions over clever ones. Ask before adding a new dependency.
