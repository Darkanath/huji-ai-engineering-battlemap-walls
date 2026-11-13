# Week 7 · 1–7.12 · Polish and freeze · Feature freeze 07.12

**Goal:** the app is ready to demo and nothing in the tracer changes after this week.

## You

- [ ] Use the app on maps it has never seen (third-party maps are fine for this; they are
      never scored or committed). Note anything confusing on the page.
- [ ] Choose the demo map(s): one where the fast pass is enough, one where the deep pass is
      worth it.
- [ ] *(optional)* Cloud deployment (course session 07.12), only if you want it; the demo
      runs on the laptop.

## Code

| File | What |
| --- | --- |
| `app/main.py`, `app/service.py` | Small fixes from your notes (wording, layout). No new features. |
| `docker-compose.yml` | The default command starts the app, so `docker compose up` is enough for the demo. |
| `README.md` | Final: what the app does, how to run it, cost and privacy, measured results, link to the system card. |

## Done when

- [ ] Your notes are fixed or written down as known limitations.
- [ ] The harness (prompt, views, profiles, config) is frozen; its last scores are in
      `docs/results.md`.
- [ ] All tests pass; `ruff` clean. **Feature freeze.**
