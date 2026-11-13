"""Trace maps with Claude, save the results and score them where labels exist.

    python -m llm.run --reference --profile quick --detect-size   (the committed reference maps)
    python -m llm.run --maps dd07_a dd06_a --profile deep --run opus   (maps from the manifest)
    python -m llm.run --image data/test/map-26x28.jpeg --squares 26 28 --run tavern
    python -m llm.run --reference --size-only    (only the map-size step, about $0.03 per map)

Paid: before the first call it prints the number of maps and the estimated cost and asks to
continue (skip with --yes). Each map gets a folder runs/<run>/<map>/ with answer.json, the
.dd2vtt (image embedded), a preview, the images the model saw (views/), trace.json (tool calls,
tokens, cost estimate) and responses.json (the model's text and tool calls, no images).
runs/<run>/summary.csv has one row per map. Without --run the folder is
runs/<YYYYMMDD-HHMMSS>_<profile>/. Maps already traced in the run are skipped, so a run can be
resumed without paying twice; use --redo to trace them again.
"""

import argparse
import csv
import io
import json
import time
from datetime import datetime
from pathlib import Path

import anthropic
from PIL import Image

from data.manifest import read_manifest
from data.rasterize import JPEG_QUALITY, decode_image, load_uvtt, overlay, rasterize_mask
from eval.metrics import portal_recall, score
from llm.agent import Trace, detect_map_size, load_config, size_step_config, trace_map
from postprocess.uvtt import answer_to_uvtt, write_uvtt

SCORE_KEYS = ("iou_wall", "boundary_f1_wall", "iou_portal", "iou_light")
ROOT = Path(__file__).parents[1]
RUNS = ROOT / "runs"
DEFAULT_MANIFEST = ROOT / "data" / "processed" / "manifest.csv"  # built by data.manifest
REFERENCE = ROOT / "data" / "reference"
PPG = 32  # the scale every answer is scored at (CLAUDE.md, Evaluation)


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
    (out / "responses.json").write_text(json.dumps(trace.responses, indent=1))
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


class Job:
    """One map to trace: its name, image, true size and, where known, its labels."""

    def __init__(self, name: str, image: Image.Image, size: tuple[int, int], label=None):
        """`label` is the map's own .dd2vtt dict, when it has one."""
        self.name, self.image, self.size, self.label = name, image, size, label


def reference_jobs(folder: Path | None = None) -> list[Job]:
    """Every .dd2vtt in `folder` (default data/reference/): image, true size and labels all
    from the file itself."""
    jobs = []
    for path in sorted((folder or REFERENCE).glob("*.dd2vtt")):
        uvtt = load_uvtt(path)
        size = (uvtt["resolution"]["map_size"]["x"], uvtt["resolution"]["map_size"]["y"])
        ppg = uvtt["resolution"]["pixels_per_grid"]
        jobs.append(Job(path.stem, decode_image(uvtt, ppg), size, uvtt))
    return jobs


def manifest_jobs(manifest: Path, maps: list[str]) -> list[Job]:
    """Maps named from the manifest, with labels from their raw .dd2vtt when it is present."""
    processed = manifest.parent
    rows = {r["map"]: r for r in read_manifest(manifest)}
    jobs = []
    for m in maps:
        row = rows[m]
        raw = ROOT / "data" / "raw" / row["dataset"] / f"{m}.dd2vtt"
        label = load_uvtt(raw) if raw.exists() else None
        image = Image.open(processed / row["image"]).convert("RGB")
        jobs.append(Job(m, image, (int(row["width"]), int(row["height"])), label))
    return jobs


def estimate_per_map(cfg: dict, profile: str) -> float:
    """The profile's measured cost per map, scaled by token price when --model replaced its
    model (the token count is assumed the same; an --effort change is not accounted for)."""
    base = cfg["profiles"][profile]
    per_map = base["expected_cost_usd"]
    if cfg["model"]["name"] != base["name"]:
        old, new = cfg["prices"][base["name"]], cfg["prices"][cfg["model"]["name"]]
        per_map *= new["output"] / old["output"]
    return per_map


def confirm(n_maps: int, per_map: float, assume_yes: bool, note: str = "") -> bool:
    """Print the estimated cost and ask before any paid call (unless `assume_yes`)."""
    print(f"{n_maps} maps, estimated cost about ${n_maps * per_map:.2f} (${per_map:.2f} per map).")
    if note:
        print(note)
    if assume_yes:
        return True
    return input("Continue? [y/N] ").strip().lower() in ("y", "yes")


def score_row(uvtt: dict, label: dict) -> dict:
    """Pixel and boundary scores at 32 px per square, and portal recall, against a label."""
    pred = rasterize_mask({**uvtt, "image": ""}, PPG)
    true = rasterize_mask({**label, "image": ""}, PPG)
    scores = score(pred, true, PPG)
    row = {k: round(float(scores[k]), 4) for k in SCORE_KEYS}
    row["portal_recall"] = round(portal_recall(uvtt, label), 4)
    return row


def size_row(out: Path, job: Job, detected, trace: Trace, seconds: float) -> dict:
    """Save one map's size-step responses to size.json and return its summary row."""
    out.mkdir(parents=True, exist_ok=True)
    (out / "size.json").write_text(json.dumps(trace.responses, indent=1))
    return {
        "map": job.name,
        "model": sorted(trace.served_by)[0] if trace.served_by else "",
        "stopped": trace.stopped,
        "true_size": f"{job.size[0]}x{job.size[1]}",
        "detected_size": f"{detected[0]}x{detected[1]}" if detected else "none",
        "size_right": detected == tuple(job.size),
        "size_cost_usd": round(trace.cost_usd, 3),
        "seconds": round(seconds, 1),
    }


def main(argv: list[str] | None = None) -> None:
    """Command-line entry point."""
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--maps", nargs="+", default=[], help="map names from the manifest")
    ap.add_argument("--reference", action="store_true", help="trace the maps in data/reference/")
    ap.add_argument("--image", type=Path, help="any map image, with --squares")
    ap.add_argument("--squares", nargs=2, type=int, metavar=("W", "H"))
    ap.add_argument("--run", help="run folder name under runs/ (default: timestamp_profile)")
    ap.add_argument("--profile", choices=("quick", "deep"), default="quick")
    ap.add_argument("--model", help="override the profile's model")
    ap.add_argument("--effort", help="override the profile's effort")
    ap.add_argument("--detect-size", action="store_true", help="let the model find the map size")
    ap.add_argument(
        "--size-only",
        action="store_true",
        help="run only the map-size step (no tracing); implies --detect-size",
    )
    ap.add_argument("--yes", action="store_true", help="skip the cost confirmation")
    ap.add_argument("--redo", action="store_true", help="trace maps again even if already done")
    ap.add_argument("--manifest", type=Path, default=DEFAULT_MANIFEST)
    args = ap.parse_args(argv)

    cfg = load_config(args.profile)
    if args.model:
        cfg["model"]["name"] = args.model
    if args.effort:
        cfg["model"]["effort"] = args.effort
    jobs = manifest_jobs(args.manifest, args.maps) if args.maps else []
    if args.reference:
        jobs += reference_jobs()
    if args.image:
        jobs.append(
            Job(args.image.stem, Image.open(args.image).convert("RGB"), tuple(args.squares))
        )

    run_dir = RUNS / (args.run or f"{datetime.now():%Y%m%d-%H%M%S}_{args.profile}")
    args.detect_size = args.detect_size or args.size_only
    marker = "size.json" if args.size_only else "trace.json"
    todo = [j for j in jobs if args.redo or not (run_dir / j.name / marker).exists()]
    for job in jobs:
        if job not in todo:
            print(f"{job.name}: already traced, skipping (use --redo)")
    if not todo:
        return
    note = ""
    if args.model or args.effort:
        note = (
            f"The estimate is the {args.profile} profile's measured cost, scaled to "
            f"{cfg['model']['name']}'s token price; effort changes are not included."
        )
    per_map = (
        size_step_config()["size_step"]["expected_cost_usd"]
        if args.size_only
        else estimate_per_map(cfg, args.profile)
    )
    if not confirm(len(todo), per_map, args.yes, note):
        print("Stopped; nothing was sent.")
        return

    client = anthropic.Anthropic()
    summary = []
    for job in todo:
        out = run_dir / job.name
        start = time.time()
        trace = Trace()
        detected = None
        if args.detect_size:
            # The same size step as the app: the [size_step] profile's model, priced as such.
            detected = detect_map_size(job.image, size_step_config(), client, trace)
        size_cost = trace.cost_usd
        if args.size_only:
            summary.append(size_row(out, job, detected, trace, time.time() - start))
            print(", ".join(f"{k} {v}" for k, v in summary[-1].items()))
            continue
        # Always traced and scored on the true size, so scores stay comparable across runs.
        trace_map(job.image, job.size, cfg, client, views_dir=out / "views", trace=trace)
        uvtt = save_map(out, job.name, job.image, job.size, trace, time.time() - start)
        row = {
            "map": job.name,
            "profile": args.profile,
            "model": cfg["model"]["name"],
            "effort": cfg["model"]["effort"],
            "stopped": trace.stopped,
            "turns": trace.turns,
            "views": trace.views,
            "submissions": trace.submissions,
            "cost_usd": round(trace.cost_usd, 3),
            "seconds": round(time.time() - start),
            "true_size": f"{job.size[0]}x{job.size[1]}",
        }
        if args.detect_size:
            row["detected_size"] = f"{detected[0]}x{detected[1]}" if detected else "none"
            row["size_right"] = detected == tuple(job.size)
            row["size_cost_usd"] = round(size_cost, 3)
        if uvtt is not None and job.label is not None:
            row.update(score_row(uvtt, job.label))
        summary.append(row)
        print(", ".join(f"{k} {v}" for k, v in row.items()))

    path = run_dir / "summary.csv"
    old = list(csv.DictReader(path.open())) if path.exists() else []
    done = {r["map"] for r in summary}
    allrows = [r for r in old if r["map"] not in done] + summary
    fields = list(dict.fromkeys(k for r in allrows for k in r))
    with path.open("w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fields)
        writer.writeheader()
        writer.writerows(allrows)
    total = sum(r.get("cost_usd", r.get("size_cost_usd", 0)) for r in summary)
    print(f"total estimated cost this call: ${total:.2f}")
    print(f"run folder: {run_dir}")


if __name__ == "__main__":
    main()
