"""Trace maps with Claude, save the results and score them where labels exist.

    python -m llm.run --maps dd07_a dd06_a --run claude_opus      (maps from the manifest)
    python -m llm.run --image data/test/map-26x28.jpeg --squares 26 28 --run tavern

Each map gets a folder runs/<run>/<map>/ with answer.json, the .dd2vtt (image embedded), a
preview, the images the model saw (views/) and trace.json (tool calls, tokens, cost estimate).
runs/<run>/summary.csv has one row per map. Maps already traced in the run are skipped, so a
run can be resumed without paying twice; use --redo to trace them again.
"""

import argparse
import csv
import io
import json
import time
from pathlib import Path

import numpy as np
from PIL import Image

from data.manifest import read_manifest
from data.rasterize import JPEG_QUALITY, overlay, rasterize_mask
from eval.evaluate import DEFAULT_MANIFEST, PPG, RUNS
from eval.metrics import score
from llm.agent import Trace, load_config, trace_map
from postprocess.uvtt import answer_to_uvtt, write_uvtt

SCORE_KEYS = ("iou_wall", "boundary_f1_wall", "iou_portal", "iou_light")


def save_map(
    out: Path,
    name: str,
    image: Image.Image,
    map_size: tuple[int, int],
    trace: Trace,
    seconds: float,
) -> dict | None:
    """Write one map's files; returns the .dd2vtt dict (None if there was no answer)."""
    out.mkdir(parents=True, exist_ok=True)
    info = {
        k: getattr(trace, k)
        for k in (
            "turns",
            "views",
            "submissions",
            "input_tokens",
            "output_tokens",
            "cache_write_tokens",
            "cache_read_tokens",
            "cost_usd",
            "stopped",
            "note",
            "log",
        )
    }
    info.update(served_by=sorted(trace.served_by), seconds=round(seconds, 1))
    (out / "trace.json").write_text(json.dumps(info, indent=1))
    if trace.answer is None:
        return None
    (out / "answer.json").write_text(json.dumps(trace.answer, indent=1))
    buf = io.BytesIO()
    image.save(buf, format="JPEG", quality=JPEG_QUALITY)
    ppg = round(image.width / map_size[0])
    uvtt = answer_to_uvtt(trace.answer, map_size, ppg, buf.getvalue())
    write_uvtt(out / f"{name}.dd2vtt", uvtt)
    preview = overlay(image, rasterize_mask(uvtt, ppg))
    preview.save(out / "preview.jpg", quality=JPEG_QUALITY)
    return uvtt


def main(argv: list[str] | None = None) -> None:
    """Command-line entry point."""
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--maps", nargs="+", default=[], help="map names from the manifest")
    ap.add_argument("--image", type=Path, help="any map image, with --squares")
    ap.add_argument("--squares", nargs=2, type=int, metavar=("W", "H"))
    ap.add_argument("--run", required=True, help="run folder name under runs/")
    ap.add_argument("--model", help="override the model in the config")
    ap.add_argument("--effort", help="override the effort in the config")
    ap.add_argument("--redo", action="store_true", help="trace maps again even if already done")
    ap.add_argument("--manifest", type=Path, default=DEFAULT_MANIFEST)
    args = ap.parse_args(argv)

    cfg = load_config()
    if args.model:
        cfg["model"]["name"] = args.model
    if args.effort:
        cfg["model"]["effort"] = args.effort
    processed = args.manifest.parent
    rows = {r["map"]: r for r in read_manifest(args.manifest)} if args.maps else {}
    jobs = [
        (m, processed / rows[m]["image"], (int(rows[m]["width"]), int(rows[m]["height"])))
        for m in args.maps
    ]
    if args.image:
        jobs.append((args.image.stem, args.image, tuple(args.squares)))

    run_dir = RUNS / args.run
    summary = []
    for name, path, map_size in jobs:
        out = run_dir / name
        if (out / "trace.json").exists() and not args.redo:
            print(f"{name}: already traced, skipping (use --redo)")
            continue
        image = Image.open(path).convert("RGB")
        start = time.time()
        trace = trace_map(image, map_size, cfg, views_dir=out / "views")
        uvtt = save_map(out, name, image, map_size, trace, time.time() - start)
        row = {
            "map": name,
            "model": cfg["model"]["name"],
            "effort": cfg["model"]["effort"],
            "stopped": trace.stopped,
            "turns": trace.turns,
            "views": trace.views,
            "submissions": trace.submissions,
            "cost_usd": round(trace.cost_usd, 3),
            "seconds": round(time.time() - start),
        }
        if uvtt is not None and name in rows:
            true = np.array(Image.open(processed / rows[name]["mask_32"]))
            scores = score(rasterize_mask({**uvtt, "image": ""}, PPG), true, PPG)
            row.update({k: round(float(scores[k]), 4) for k in SCORE_KEYS})
        summary.append(row)
        print(", ".join(f"{k} {v}" for k, v in row.items()))

    if summary:
        path = run_dir / "summary.csv"
        old = list(csv.DictReader(path.open())) if path.exists() else []
        done = {r["map"] for r in summary}
        allrows = [r for r in old if r["map"] not in done] + summary
        fields = list(dict.fromkeys(k for r in allrows for k in r))
        with path.open("w", newline="") as f:
            writer = csv.DictWriter(f, fieldnames=fields)
            writer.writeheader()
            writer.writerows(allrows)
        print(f"total estimated cost this call: ${sum(r['cost_usd'] for r in summary):.2f}")


if __name__ == "__main__":
    main()
