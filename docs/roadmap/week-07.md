# Week 7 · 1–7.12 · App polish, request log, demo setup · Feature freeze 07.12

**Goal:** the app is ready to demonstrate, changed only where the evaluation showed a need. No
new features after 07.12.

## You

- [ ] Try the app with maps it has never seen; note anything confusing in the UI.
- [ ] Rehearse the demo path once on the presentation network, and record a backup video.
- [ ] Session 30 (07.12, cloud deployment) *(optional)*: only after everything runs locally.
      A public deployment would spend your API budget for anyone who opens it, so it needs a
      cost cap and your explicit go-ahead.

## Code

| File | What |
| --- | --- |
| `app/service.py`, `app/main.py` | Fixes from week 6: wording of the deep-pass note and the expected time and cost on the buttons, updated to the measured values. |
| `llm/agent.py`, `llm/configs/claude.toml` | Only changes the evaluation supports, re-scored on the reference maps before they are kept. Freeze the harness at the end of the week. |
| `app/request_log.py` | Per pass: profile, model, time, estimated cost, map size, wall, portal and light count, outcome. Written under `runs/`; never the image or the key. |
| `tests/test_request_log.py` | A pass and a failed pass each write one line with the right fields. |
| `docker-compose.yml` | Default command starts the app on port 7860. |

## Run

```bash
docker compose up app        # then open http://localhost:7860
docker compose run --rm app pytest
```

## Done when

- [ ] The buttons show measured expectations from the full evaluation.
- [ ] The harness (prompt, views, profiles) is frozen and its reference scores recorded.
- [ ] A backup demo video exists.
- [ ] All tests pass. **Feature freeze.**

## Report

- Time and cost per pass from the request log, for the demo slide.

## Dependencies

None new.
