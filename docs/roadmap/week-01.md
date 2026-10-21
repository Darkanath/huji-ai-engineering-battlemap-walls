# Week 1 · 20–26.10 · Setup, rasterizer, labeling rules, first maps

**Goal:** a working Docker setup, a tested .dd2vtt -> mask rasterizer, written labeling rules, and
the first Dungeondraft maps checked against those rules.

## You

- [x] Make 3 Dungeondraft layouts at 25×25 squares, Roll20 grid preset: `dd01_a`, `dd02_a`, `dd03_a`.
- [x] Export variants `b`, `c` and `d` of each layout (different wall style, floor texture; `d`
      without grid). Shadows off on furniture. Name them `dd01_b.dd2vtt` ... `dd01_d.dd2vtt`.
- [x] Upload `demo-training-map.dd2vtt` to Roll20 (Page Menu -> Upload Background). Check that the
      walls and doors appear and fog of war works. Done 20.10: the Dungeondraft exports work in
      Roll20.
- [ ] *(optional)* Try a .dd2vtt whose embedded image is JPEG, to see whether output files can be
      lighter. If not done this week, it moves to week 5's Roll20 test.
- [ ] Confirm with the course staff what the final submission must include (still open in PLAN.md).
- [ ] **Lights (added 21.10):** add at least 3 lit light sources of two or more tiers to each of
      `dd01`–`dd03`, each with a Dungeondraft light at its tier's `range` (labeling rules, "Light
      (class 3)"), and re-export all 12 variants with the same lights. If not done this week, it
      moves to week 2.
- [ ] Upload the re-exported `dd01_a.dd2vtt` to Roll20 and note how each tier's light imports
      (bright and dim radius from `range` and `intensity`) in `docs/labeling-rules.md`. Also check
      that `range` in the .dd2vtt is in grid squares. If not done this week, it moves to week 2.

## Code

| File | What | Status |
| --- | --- | --- |
| `Dockerfile`, `docker-compose.yml` | Ubuntu 24.04, Python 3.12 venv, CPU-only torch; `data/`, `runs/`, `tests/` volumes | done |
| `pyproject.toml` | Package config, ruff, pytest; minimal dependencies | done |
| `data/rasterize.py` | .dd2vtt -> JPEG image + PNG class mask + preview | done |
| `tests/test_rasterize.py` | 7 tests: demo map and a hand-made map | done |
| `docs/labeling-rules.md` | Classes, edge cases, Dungeondraft and hand-tracing checklists | done |
| `docs/dungeondraft-maps.md` | Log of the Dungeondraft maps | done |
| `data/rasterize.py` | Lights: tier from `range` (error on an unknown range), disc per tier drawn under walls and portals, lights in the preview | to do |
| `tests/test_rasterize.py` | A hand-made map with one light per tier: disc sizes right; a light next to a wall leaves the wall unbroken; an unknown range raises | to do |

## Run

```bash
docker compose build
docker compose run --rm app pytest
docker compose run --rm app sh -c 'for f in data/raw/dungeondraft/dd*.dd2vtt; do python -m data.rasterize "$f" --out data/processed/dungeondraft; done'
```

Open each `_preview.jpg` in `data/processed/dungeondraft/`: red only on walls, magenta only on
doors and windows, light discs only on lit light sources.

## Done when

- [x] `docker compose run --rm app pytest` passes; `ruff check` is clean.
- [x] Labeling rules written and linked from the README.
- [x] 3 layouts × 4 variants exported, rasterized and checked; `docs/dungeondraft-maps.md` updated.
- [x] A .dd2vtt uploaded to Roll20 with working walls and doors.
- [ ] Rasterizer labels lights; `dd01`–`dd03` re-exported with lights and checked (may slip to week 2).

## Report

- First class pixel shares (walls 4.8–7.4%, portals 0.2–1.1%): the start of the data summary.

## Dependencies

numpy, Pillow (runtime); pytest, ruff (dev); torch, torchvision (CPU wheels, in the Dockerfile).
