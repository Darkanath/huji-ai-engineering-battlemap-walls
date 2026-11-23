# Lessons log

What didn't work, what surprised us and what changed the plan, one dated line each. The
presentation's "what we learned" slide comes from this page (course brief: share what didn't
work as well as what did).

| Date | What happened | What changed |
| --- | --- | --- |
| 21.10 | The .dd2vtt has no door/window type | One portal class for both |
| 21.10 | Dungeon Alchemist light ranges are per asset, not per tier | `data/retier_lights.py` maps them to tiers |
| 26.10 | Crops centered on a wall near the map edge get shifted inward, so the wall is no longer in the center | Expected; the crop still holds the wall, and the test checks only crops away from the edge |
| 26.10 | MLflow 3 refuses its plain-file tracking store by default | Opted in (`MLFLOW_ALLOW_FILE_STORE`): files work on Google Drive, SQLite doesn't reliably |
| 26.10 | EDA: real Dungeondraft maps are brighter than most synthetic maps (mean brightness 100–170 vs 20–140), and have less wall per map (wall share 4.7% vs 8.7%; labels have a fixed width, so this is wall length, not thickness) | Expected gap; stage 2 fine-tuning on real maps is there for it. Revisit the generator's brightness range if R1 transfers badly |
| 26.10 | Colab: pretrained weights cached on Google Drive loaded as corrupt ("header too large"); a file just written through the Drive mount can read back incomplete | Weights cache on Colab's local disk (downloads once per session); only checkpoints and logs go to Drive |
| 26.10 | R1 epoch 1 labels every wall as a portal | Class weights push toward rare classes early; gone by epoch 6. Shown in the learning-progression figure |
| 26.10 | R1 real-val boundary F1 plateaus (~0.84) while the training loss keeps falling | Synthetic-to-real gap; stage 2 fine-tuning on real maps. More real val layouts needed: one layout makes the best-epoch choice noisy |
| 26.10 | R1 predicts a few light specks on light-free `dd03` (light IoU 0) | Minimum blob size in light post-processing (week 6) |
| 26.10 | Colab EDA: `No module named 'data.rasterize'`. The pack was unzipped to `/content/data/`, and with `/content` as the working folder `import data` found that folder (a namespace package) instead of the project's `data` package | Both notebooks unzip to `/content/pack`; the EDA notebook also imports the project from its clone |
| 13.11 | A spike showed Claude tracing walls, portals and lights straight from the image, far ahead of the stage-1 U-Net on two real maps (boundary F1 0.995 / 0.957 vs 0.664 / 0.118), after the course staff allowed a large model | Training dropped; the Claude tracer became the core, the U-Net a comparison row |
| 13.11 | Tracer v1: left to choose when to zoom in, Sonnet and Haiku barely looked and missed the cave walls; Opus missed tower doors | v2 sends the four map quarters up front; every model improved |
| 13.11 | Higher effort did not beat medium on the two maps tried | Both profiles run at medium effort |
| 23.11 | Planning the chunked pass: on the 25 x 25 reference maps (70 px per square) the tracer's quarter views are already shown at about 96 px per square, above the image's own resolution, so smaller chunks cannot add detail there | Chunking is measured as a gain in focus (each agent its own area and budget of closer views), not resolution; the spec's "more pixels than the quarters" was corrected to "never less than the image's own" |
| 23.11 | First live Haiku runs with 16 parts: walls joined wrongly and pieces missing. Seams fell on whole squares where grid-aligned walls are drawn, ends were snapped in chains (and within one part), and only ends exactly on a seam were joined. The label-cut test missed it because perfect agents agree to the last decimal | Seams at quarter squares, one-to-one joins across the seam (never through a door), ends near a seam joined too; a seeded test with imperfect agents on a grid-aligned map (F1 0.49 before, 0.95 after) |
| 23.11 | Merging chunk answers by distance-matching duplicates needs a threshold per item type and still keeps both copies when agents disagree | Merge by ownership instead: the cores partition the map and each chunk keeps only what lies in its own core; a test merges real labels cut into chunks with no loss |
