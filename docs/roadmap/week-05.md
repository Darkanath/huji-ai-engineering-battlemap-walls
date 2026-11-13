# Week 5 · 17–23.11 · The app · Milestone: a file from the app imports into Roll20

**Goal:** the web app works end to end: upload, fast suggestion, deeper examination, accept,
download. The tasks, in order, are in `specs/001-battlemap-tracer-app/tasks.md`; this file
lists the pieces and what closes the week.

## You

- [x] Approve `gradio` being added (already agreed in CLAUDE.md). Installed 13.11 with `pydantic`, under `uv`.
- [ ] Try the app on `data/test/map-26x28.jpeg` (26 x 28 squares): fast pass, deep pass, accept
      as `.dd2vtt` and as `.uvtt`. About $0.35 in paid calls.
- [ ] **Milestone:** upload a file downloaded from the app to Roll20 (Page Menu -> Upload
      Background) and check that fog of war follows the walls.

## Code

| File | What |
| --- | --- |
| `llm/configs/claude.toml` | Two profiles: `quick` (Sonnet 5.5) and `deep` (Opus 5.5), medium effort. |
| `llm/agent.py` | `load_config(profile="quick")`; the model also works out the map size when it is not given, in the same pass. |
| `llm/run.py` | `--profile quick|deep`; `--model` and `--effort` still override. |
| `app/service.py` | App logic as plain functions: check the upload (type, 20 MB, map size 1–200), run a pass, draw the preview, rescale the mask when the map size changes, write the export file. Every failure cause becomes a plain-language message. |
| `app/main.py` | The Gradio page: upload, map size with "detect from the image", "Suggest walls", "Deeper examination" with its note, "Accept mask" with the extension choice, progress with elapsed time, status line. Only wires controls to `app/service.py`. |
| `tests/test_app_service.py` | With the fake client: a pass returns a preview and an answer; the deep profile asks for the Opus model; each failure cause gives a message and keeps the earlier mask; a rejected upload makes no call; the export reads back with `load_uvtt` at 70 px per square for both extensions; a changed map size keeps the mask over the same image features. |
| `tests/test_llm_agent.py` | The profiles pick the right models; a detected map size is returned with the answer; no grid found falls back to the given size. |

## Run

```bash
docker compose build
docker compose run --rm app pytest
docker compose run --rm app ruff check . && docker compose run --rm app ruff format --check .
docker compose run --rm --service-ports app python -m app.main   # then open http://localhost:7860
```

## Done when

- [ ] Upload -> suggest -> deeper examination -> accept -> download works in the browser.
- [x] Each paid button shows its expected time and cost; the status line shows the actual ones.
- [x] Every failure cause in the spec shows a message, never a stack trace, and the earlier
      mask stays (fake-client tests in `tests/test_app_tracer.py` and `tests/test_app_service.py`).
- [ ] A file downloaded from the app imports into Roll20. **Milestone.**
- [x] All tests pass; `ruff` clean (13.11: 244 tests).

## Report

- Screenshots of the app for the demo slide; time and cost of the first real passes.

## Dependencies

- `gradio` (in CLAUDE.md).
