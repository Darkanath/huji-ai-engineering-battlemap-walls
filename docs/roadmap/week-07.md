# Week 7 · 1–7.12 · Gradio app, ONNX, deploy · Feature freeze 07.12

**Goal:** a web demo: upload a map, see the predicted walls over it, download the .dd2vtt. Served
with ONNX Runtime on CPU, in the same Docker image. No new features after 07.12.

## You

- [ ] Try the app with maps the model has never seen; note anything confusing in the UI.
- [ ] Session 30 (07.12, cloud deployment) *(stretch)*: push the image to a cloud service.

## Code

| File | What |
| --- | --- |
| `train/export_onnx.py` | Export the chosen checkpoint to `runs/<run>/model.onnx`; check ONNX and PyTorch outputs match on the demo map. |
| `train/predict.py` | Add an ONNX Runtime backend next to the PyTorch one. |
| `app/app.py` | Gradio UI: image upload (`.png`, `.jpg`/`.jpeg`, `.webp`), map width in squares pre-filled with 25 (used when no grid is found), overlay preview, .dd2vtt download. |
| `app/request_log.py` | Per request: inference time, map size, wall and portal count, to a log file under `runs/`. |
| `docker-compose.yml` | Default command starts the app on port 7860. |
| `tests/test_onnx.py` | ONNX and PyTorch predictions agree on the demo map. |
| `tests/test_app.py` | The app's predict function returns a preview image and a valid .dd2vtt. |

FastAPI stays optional: add it only if the cloud deployment needs a plain API.

## Run

```bash
docker compose run --rm app python -m train.export_onnx --run <chosen-run>
docker compose up app        # then open http://localhost:7860
```

## Done when

- [ ] Upload -> preview -> download works in the browser.
- [ ] A map downloaded from the app imports into Roll20.
- [ ] All tests pass. **Feature freeze.**

## Report

- Inference time per map on CPU (PyTorch vs ONNX), for the deployment slide.

## Dependencies

- `gradio`, `onnxruntime` (in CLAUDE.md).
- `onnx`: **new, ask first.** `torch.onnx.export` needs it to write the model file.
- `fastapi`, `uvicorn` only if needed (in CLAUDE.md).
