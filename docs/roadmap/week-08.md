# Week 8 · 8–14.12 · Write-up: system card, failure gallery, exhibits

**Goal:** everything the presentation shows exists as a file. Writing only; no paid runs.

## You

- [ ] Workshop session 14.12: show the results and the app, collect feedback.
- [ ] Record the demo video (about 2 minutes): map image -> app -> file -> Roll20 fog of war.
      It is also the backup if the live demo fails.

## Code and docs

| File | What |
| --- | --- |
| `docs/system-card.md` | Intended use; the models and why (measured); what is sent to Anthropic and what never leaves the laptop; results with sample sizes; known limitations (fast pass misses doors, caves are harder, map-size detection fails on faint grids and is off by default); cost per map; how failures reach the user. |
| `docs/failure-gallery.md` | Four to six failures from existing runs, each with its image and one sentence on why: fast pass with no doors on the castle, the mine on the fast pass, the lakeside map's 56 x 32, and the false grid from floor tiles. |
| `docs/exhibits/` | The images the slides use: before/after previews, the results chart, a Roll20 screenshot. |

## Done when

- [ ] System card and failure gallery written, every number traceable to `docs/results.md`.
- [ ] Exhibits ready for the slides.
- [ ] Demo video recorded.
