# huji-ai-engineering-battlemap-walls

Course project for AI Engineering (Hebrew University). Upload a top-down battlemap image and get
back a Universal VTT file (`.dd2vtt` or `.uvtt`) with **walls**, **portals** (doors and windows)
and **light sources** already placed, ready to upload to Roll20 for dynamic lighting and fog of
war.

The core is a **Claude wall tracer**: a large vision model looks at the map (the whole image,
its four quarters at higher zoom, and closer crops it asks for), answers with walls, portals and
lights in grid squares, and checks its answer drawn over the map. A small writer turns the answer
into the file. Each light's brightness comes from its size tier (small: torch, medium: brazier,
large: bonfire) and a lookup table, since an image does not show how far a light reaches.

- Input: `.png`, `.jpg`/`.jpeg` or `.webp` image
- Output: `.dd2vtt` / `.uvtt` (walls, portals, lights, embedded map image), at 70 px per grid square
- Runs on a laptop CPU, under Docker. Tracing calls the Anthropic API: it needs a key and
  network access, costs money per map, and sends the map image to Anthropic.

Two passes, measured on the labeled reference maps (one to three runs per map,
[`docs/results.md`](docs/results.md)). Both include the map-size step, which runs on Opus in
either pass:

| Pass | Model | Time per map | Cost per map | Wall boundary F1, castle / mine |
| --- | --- | --- | --- | --- |
| Fast ("Suggest walls") | Claude Sonnet 5.5 | about 25 s | about $0.10 | 0.91–0.97 / 0.55–0.66 |
| Deep ("Deeper examination") | Claude Opus 5.5 | about 70 s | about $0.32 | 0.99 / 0.88–0.89 |

**The first approach** (weeks 1–3) was a U-Net trained on synthetic maps. On 13.11.2026 the
course staff allowed a large model in place of a trained one, and the tracer scored far ahead of
the stage-1 U-Net on real maps, so training stopped. The generator, training code and results
stay in the repo as that record and as a comparison row.

See [`docs/PLAN.md`](docs/PLAN.md) for the full plan and evaluation,
[`specs/001-battlemap-tracer-app/spec.md`](specs/001-battlemap-tracer-app/spec.md) for what the
app does, and [`docs/roadmap/`](docs/roadmap/README.md) for week-by-week tasks.

## Status

Week 4 of 9 (final presentation 2026-12-23).

- [x] Repo layout, Docker setup
- [x] `.dd2vtt` -> class mask rasterizer, with light labels and tests
- [x] Metrics (pixel IoU, wall boundary F1), Canny baseline, evaluation harness
- [x] Real maps: Dungeondraft `dd01`–`dd08`, Dungeon Alchemist `da01` (34 maps)
- [x] First approach: synthetic generator, manifest, stage-1 U-Net (training stopped here)
- [x] Claude wall tracer (`llm/`) and model comparisons
- [x] `.dd2vtt` writer; a traced map imported into Roll20 with working fog of war
- [x] App spec and project constitution
- [x] Gradio app: fast pass, deep pass, accept and download (tested with a fake model client)
- [x] Map size worked out by the model during a pass (built; accuracy not measured yet)
- [ ] Reference evaluation of both passes with the map-size step (paid; needs approval)
- [x] Roll20 import of a file downloaded from the app
- [ ] Results table from the existing runs
- [ ] System card, failure gallery, presentation (23.12)

## Quick start

Requires Docker with Docker Compose. On Windows, enable WSL integration in Docker Desktop.

```bash
docker compose build                    # Ubuntu 24.04, Python 3.12, CPU-only PyTorch, uv.lock
docker compose run --rm app pytest      # run the tests (no paid calls)
docker compose run --rm app ruff check  # lint
```

Dependencies are declared in `pyproject.toml` and locked in `uv.lock`; the image installs
them with `uv sync --frozen`. After changing a dependency, run `uv lock` and rebuild.

To trace maps, put your Anthropic API key in a `.env` file in the repo root (gitignored):

```bash
ANTHROPIC_API_KEY=...
```

Start the app (served at http://localhost:7860):

```bash
docker compose run --rm --service-ports app python -m app.main
```

Upload a map image, click "Suggest walls" (fast pass, about 25 s and $0.10) and, if needed,
"Deeper examination" (about 70 s and $0.32), then "Accept mask" to download the `.dd2vtt` or
`.uvtt`. Each button shows its expected time and cost; the status line shows what the pass
actually took. The image is sent to Anthropic for analysis.

Trace the reference maps and score them. **This calls the API and costs money** (about $0.10
per map for the `quick` profile, $0.32 for `deep`; `llm/configs/claude.toml` has the profiles,
the limits and a cost cap per map). It prints the estimate and asks before the first call:

```bash
docker compose run --rm app python -m llm.run --reference --profile quick --detect-size
```

Answers, the model's responses, previews, the .dd2vtt files and scores are written to
`runs/<timestamp>_<profile>/` (or `--run NAME`); `--maps dd07_a dd06_a` traces maps from the
manifest instead.

Rasterize a `.dd2vtt` into an image, a class mask and a preview overlay (free, local):

```bash
docker compose run --rm app python -m data.rasterize \
    data/raw/dungeondraft/demo-training-map.dd2vtt --out data/processed/demo
```

Mask classes: `0` background, `1` wall, `2` portal, `3` light. Masks are always PNG so class ids
stay exact.

Score the Canny baseline on a split (per-map and mean metrics in `runs/<predictor>_<split>/metrics.csv`):

```bash
docker compose run --rm app python -m eval.evaluate --predictor canny --split val
```

Dungeon Alchemist exports set light ranges per asset, not by tier. Map them to the tiers first
(the originals in `original/` are never changed):

```bash
docker compose run --rm app python -m data.retier_lights --source dungeon_alchemist \
    data/raw/dungeon_alchemist/original/da01_a.dd2vtt --out data/raw/dungeon_alchemist
```

## Repo layout

```
llm/             Claude wall tracer: agent.py (tool loop), views.py (grid views, answer overlay),
                 run.py (batch runs and scoring), configs/claude.toml
postprocess/     uvtt.py: the tracer's answer -> .dd2vtt / .uvtt
app/             Gradio app: service.py (logic), main.py (page wiring), tracer.py (one pass),
                 exporter.py, render.py, domain.py, config.py, errors.py, logging.py
eval/            metrics (pixel IoU, boundary F1), Canny baseline, evaluate.py
data/            rasterize.py (.dd2vtt -> mask), manifest.py, retier_lights.py (other tools'
                 lights -> tiers), configs/; generator.py + synth/ (first approach)
  raw/           source .dd2vtt files: dungeondraft/, dungeon_alchemist/, synthetic/, test/
                 (gitignored, except the demo map used by the tests)
  processed/     image + mask pairs, manifest.csv (gitignored)
  reference/     four labeled maps for the tracer's reference evaluation (committed)
train/           U-Net training code (first approach, frozen)
notebooks/       eda.ipynb, colab_train.ipynb (first approach, frozen)
specs/           feature specs, plans and tasks
docs/            PLAN.md, app-plan.md, results.md, labeling-rules.md, lessons.md, map-specs.md,
                 map-log.md, training.md (history), roadmap/
runs/            run outputs: answers, previews, scores (gitignored)
tests/           pytest
```

`data/` and `runs/` are mounted into the container, so datasets and run outputs stay on the host.

## Data and licensing

The real maps were made for this project in Dungeondraft and Dungeon Alchemist; their labels come
only from `.dd2vtt` exports and are used to score the tracer. Synthetic maps trained the stage-1
U-Net. Published third-party maps are used only to try the app and are never redistributed.

## License

MIT, once the course is done.
