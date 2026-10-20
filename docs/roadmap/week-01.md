# Week 1 · 20–26.10 · Setup, rasterizer, labeling rules, first maps

**Goal:** a working Docker setup, a tested .dd2vtt -> mask rasterizer, written labeling rules, and
the first Dungeondraft maps checked against those rules.

## You

- [x] Make 3 Dungeondraft layouts at 25×25 squares, Roll20 grid preset: `dd01_a`, `dd02_a`, `dd03_a`.
- [ ] Export variants `b` and `c` of each layout (different wall style, floor texture, lighting or
      grid). Shadows off on furniture. Name them `dd01_b.dd2vtt`, `dd01_c.dd2vtt`, and so on.
- [ ] Upload `demo-training-map.dd2vtt` to Roll20 (Page Menu -> Upload Background). Check that the
      walls and doors appear and fog of war works. If you have time, also try a .dd2vtt whose
      embedded image is JPEG, to see whether output files can be lighter.
- [ ] Confirm with the course staff what the final submission must include (still open in PLAN.md).

## Code

| File | What | Status |
| --- | --- | --- |
| `Dockerfile`, `docker-compose.yml` | Ubuntu 24.04, Python 3.12 venv, CPU-only torch; `data/`, `runs/`, `tests/` volumes | done |
| `pyproject.toml` | Package config, ruff, pytest; minimal dependencies | done |
| `data/rasterize.py` | .dd2vtt -> JPEG image + PNG class mask + preview | done |
| `tests/test_rasterize.py` | 7 tests: demo map and a hand-made map | done |
| `docs/labeling-rules.md` | Classes, edge cases, Dungeondraft and hand-tracing checklists | done |
| `docs/dungeondraft-maps.md` | Log of the Dungeondraft maps | done; add `b`/`c` variants |

## Run

```bash
docker compose build
docker compose run --rm app pytest
docker compose run --rm app sh -c 'for f in data/raw/dungeondraft/dd*.dd2vtt; do python -m data.rasterize "$f" --out data/processed/dungeondraft; done'
```

Open each `_preview.jpg` in `data/processed/dungeondraft/`: red only on walls, magenta only on
doors and windows.

## Done when

- [x] `docker compose run --rm app pytest` passes; `ruff check` is clean.
- [x] Labeling rules written and linked from the README.
- [ ] 3 layouts × 3 variants exported, rasterized and checked; `docs/dungeondraft-maps.md` updated.
- [ ] A .dd2vtt uploaded to Roll20 with working walls and doors.

## Report

- First class pixel shares (walls 4.8–7.4%, portals 0.2–1.1%): the start of the data summary.

## Dependencies

numpy, Pillow (runtime); pytest, ruff (dev); torch, torchvision (CPU wheels, in the Dockerfile).
