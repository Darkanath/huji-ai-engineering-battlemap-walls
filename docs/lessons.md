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
| 26.10 | EDA: real Dungeondraft maps are brighter than most synthetic maps (mean brightness 100–170 vs 20–140), and their walls are thinner (wall share 4.7% vs 8.7%) | Expected gap; stage 2 fine-tuning on real maps is there for it. Revisit the generator's brightness range if R1 transfers badly |
