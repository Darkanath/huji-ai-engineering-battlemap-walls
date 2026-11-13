# Contract: config and the evaluation command

## Config: `llm/configs/claude.toml`

The single `[model]` table is replaced by two profiles. `[limits]`, `[views]` and
`[prices."..."]` stay as they are. Validated by `app/config.py`.

```toml
[profiles.quick]             # "Suggest walls"
name = "claude-sonnet-5-5"
label = "Sonnet 5.5"
effort = "medium"
max_tokens = 16000
fallbacks = true
deadline_s = 60
expected_seconds = 20        # shown on the button; update after each full evaluation
expected_cost_usd = 0.07

[profiles.deep]              # "Deeper examination"
name = "claude-opus-5-5"
label = "Opus 5.5"
effort = "medium"
max_tokens = 16000
fallbacks = true
deadline_s = 180
expected_seconds = 60
expected_cost_usd = 0.27

[lights.small]               # must equal LIGHT_TIERS in data/rasterize.py (tested)
range = 8.0
intensity = 1.0
[lights.medium]
range = 12.0
intensity = 1.0
[lights.large]
range = 16.0
intensity = 1.0

[app]
max_upload_mb = 20
min_squares = 1
max_squares = 200
default_width = 25
default_height = 25
export_ppg = 70
export_jpeg_quality = 90
```

- The API key is read only from the `ANTHROPIC_API_KEY` environment variable (Docker
  Compose reads `.env`). It is not a config value.
- `load_config(profile="quick")` in `llm/agent.py` returns the config with `cfg["model"]`
  set from the chosen profile.

## Evaluation command: `python -m llm.run`

Opt-in and paid. Existing flags stay (`--maps`, `--image`, `--squares`, `--run`, `--model`,
`--effort`, `--redo`, `--manifest`). New:

| Flag | Meaning |
| --- | --- |
| `--profile quick|deep` | Which profile to run (default `quick`). `--model` and `--effort` still override |
| `--reference` | Trace the maps in `data/reference/`, scored against their own labels |
| `--detect-size` | Let the model work out the map size, and record whether it was right |
| `--yes` | Skip the cost confirmation |

Behaviour:

- Before the first call it prints the number of maps and the estimated cost
  (`expected_cost_usd` x maps) and asks to continue, unless `--yes` is given.
- Without `--run`, the run folder is `runs/<YYYYMMDD-HHMMSS>_<profile>/`.
- Per map it writes `responses.json` (raw model responses: text and tool calls, no
  images), `trace.json`, `answer.json`, `<map>.dd2vtt`, `preview.jpg` and `views/`.
- `summary.csv` has one row per map: map, profile, model, effort, stopped, turns, views,
  submissions, cost, seconds, wall IoU, wall boundary F1, portal IoU, portal recall, light
  IoU, true size, detected size, size right.
- Maps already traced in the run are skipped unless `--redo` is given.
- Scoring: `data/rasterize.py` + `eval/metrics.py` at 32 px per square, boundary F1
  tolerance 0.1 square; portal recall matches midpoints within 0.5 square, one to one.
