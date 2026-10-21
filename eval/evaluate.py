"""Run a predictor over one split of the manifest and save per-map and mean metrics.

Maps are scored at the training scale, 32 px per square: the predictor gets each map's 32 px
image (data/processed/<dataset>/32px/) and its prediction is compared with the 32 px mask
(eval/metrics.py). Results go to runs/<run>/metrics.csv: one row per map, then one mean row per
dataset, one for the real maps pooled ("real" = Dungeondraft + Dungeon Alchemist, the set that
selects checkpoints, docs/training.md) and one for everything ("all").

Usage:
  python -m eval.evaluate --predictor canny --split val [--datasets ...] [--run NAME]
"""

import argparse
import csv
import math
from collections.abc import Callable, Iterator
from pathlib import Path

import numpy as np
from PIL import Image

from data.manifest import FIXTURE, read_manifest
from eval import baseline_canny
from eval.metrics import mean_scores, score

ROOT = Path(__file__).parents[1]
DEFAULT_MANIFEST = ROOT / "data" / "processed" / "manifest.csv"
RUNS = ROOT / "runs"
PPG = 32  # the scale every model is trained and scored at
REAL = ("dungeondraft", "dungeon_alchemist")

Predictor = Callable[[np.ndarray, int], np.ndarray]


def canny() -> Predictor:
    """The Canny baseline with the parameters in its config."""
    params = baseline_canny.load_config()["params"]
    return lambda image, ppg: baseline_canny.predict(image, params, ppg)


PREDICTORS: dict[str, Callable[[], Predictor]] = {"canny": canny}


def select_rows(manifest: Path, split: str, datasets: list[str] | None = None) -> list[dict]:
    """Manifest rows of one split, optionally only some datasets; fixtures never count."""
    if split == FIXTURE:
        return []
    rows = [r for r in read_manifest(manifest) if r["split"] == split]
    return [r for r in rows if datasets is None or r["dataset"] in datasets]


def load_maps(processed: Path, rows: list[dict]) -> Iterator[tuple[dict, np.ndarray, np.ndarray]]:
    """(row, 32 px RGB image, 32 px class mask) for each manifest row."""
    for row in rows:
        image = np.array(Image.open(processed / row["image_32"]).convert("RGB"))
        mask = np.array(Image.open(processed / row["mask_32"]))
        yield row, image, mask


def evaluate(processed: Path, rows: list[dict], predictor: Predictor) -> list[dict]:
    """Score `predictor` on every map; one dict per map with its id fields and metrics."""
    results = []
    for row, image, true in load_maps(processed, rows):
        pred = predictor(image, PPG)
        ids = {k: row[k] for k in ("dataset", "map", "layout", "split")}
        results.append({**ids, **score(pred, true, PPG)})
    return results


def summarize(results: list[dict]) -> list[dict]:
    """Mean rows: per dataset, the real maps pooled, and all maps ("map" is "MEAN of N maps")."""
    datasets = sorted({r["dataset"] for r in results})
    groups = {d: [r for r in results if r["dataset"] == d] for d in datasets}
    groups["real"] = [r for r in results if r["dataset"] in REAL]
    groups["all"] = results
    summary = []
    for name, group in groups.items():
        if group:
            ids = {"dataset": name, "map": f"MEAN of {len(group)} maps", "layout": ""}
            summary.append({**ids, "split": group[0]["split"], **mean_scores(group)})
    return summary


def write_csv(path: Path, rows: list[dict]) -> None:
    """Write result rows to CSV, metrics rounded to 4 decimals."""
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=list(rows[0]))
        writer.writeheader()
        for row in rows:
            writer.writerow({k: round(v, 4) if isinstance(v, float) else v for k, v in row.items()})


def _fmt(value: float) -> str:
    """A metric for the console table ('-' for nan)."""
    return "    -" if math.isnan(value) else f"{value:5.3f}"


def main(argv: list[str] | None = None) -> None:
    """Command-line entry point."""
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--predictor", choices=sorted(PREDICTORS), required=True)
    ap.add_argument("--split", default="val")
    ap.add_argument("--datasets", nargs="+", help="default: every dataset in the split")
    ap.add_argument("--run", help="run folder name (default: <predictor>_<split>)")
    ap.add_argument("--manifest", type=Path, default=DEFAULT_MANIFEST)
    args = ap.parse_args(argv)

    rows = select_rows(args.manifest, args.split, args.datasets)
    if not rows:
        raise SystemExit(f"no maps in split {args.split!r}")
    results = evaluate(args.manifest.parent, rows, PREDICTORS[args.predictor]())
    summary = summarize(results)
    out = RUNS / (args.run or f"{args.predictor}_{args.split}") / "metrics.csv"
    write_csv(out, results + summary)

    print(f"{'dataset':18} {'maps':18}  wall IoU  wall BF1  portal IoU  light IoU")
    for s in summary:
        metrics = (s["iou_wall"], s["boundary_f1_wall"], s["iou_portal"], s["iou_light"])
        print(f"{s['dataset']:18} {s['map']:18}  " + "     ".join(_fmt(m) for m in metrics))
    print(f"-> {out}")


if __name__ == "__main__":
    main()
