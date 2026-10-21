"""Build every dataset to disk and list it in data/processed/manifest.csv.

For each .dd2vtt in the top level of data/raw/<dataset>/ (subfolders such as `original/` are
skipped), this:

1. reads the layout and variant from the name `<layout>_<variant>` (e.g. dd01_a); other names
   are their own layout (syn0001, t01);
2. gives each layout a split, per dataset, and keeps every split already in the manifest;
3. rasterizes the map at 70 px per square into data/processed/<dataset>/ (image, mask,
   preview), and writes the 32 px per square training copies into data/processed/<dataset>/32px/
   (image resized by area averaging; mask rasterized directly at 32 px, docs/training.md);
4. writes one manifest row per map: dataset, map, layout, variant, split, seed, size, class
   pixel shares, light counts per tier, and the output paths (relative to data/processed/).

Splits: Dungeondraft and Dungeon Alchemist 70/15/15 by layout, with at least one layout in val
and in test once a dataset has 3 layouts; synthetic 90/10; test/ is always test; the demo map
is a test fixture ("fixture") in no split. A new layout goes to the split furthest below its
share, in an order fixed by the seed, so adding maps never moves the ones already assigned.
Unchanged maps are not rasterized again (their outputs are newer than the .dd2vtt).

Usage:
  python -m data.manifest [--raw data/raw] [--processed data/processed] [--seed 42] [--force]
"""

import argparse
import csv
import random
import re
from collections import Counter, defaultdict
from pathlib import Path

import numpy as np
from PIL import Image

from data.rasterize import (
    CLASS_NAMES,
    LIGHT_TIERS,
    class_shares,
    decode_image,
    load_uvtt,
    parse_lights,
    rasterize_file,
    rasterize_mask,
)

DATA = Path(__file__).parent
DATASETS = ("dungeondraft", "dungeon_alchemist", "synthetic", "test")
SPLITS = {
    "dungeondraft": {"train": 0.70, "val": 0.15, "test": 0.15},
    "dungeon_alchemist": {"train": 0.70, "val": 0.15, "test": 0.15},
    "synthetic": {"train": 0.90, "val": 0.10},
}
DEMO_MAP = "demo-training-map"
FIXTURE = "fixture"
TRAIN_PPG = 32  # training and inference scale (docs/training.md)
TRAIN_JPEG_QUALITY = 95
NAME = re.compile(r"^([a-z]+\d+)_([a-z])$")
COLUMNS = [
    "dataset",
    "map",
    "layout",
    "variant",
    "split",
    "seed",
    "width",
    "height",
    "source_ppg",
    *(f"share_{name}" for name in CLASS_NAMES.values()),
    *(f"lights_{tier}" for tier in LIGHT_TIERS),
    "image",
    "mask",
    "image_32",
    "mask_32",
]


def parse_name(stem: str) -> tuple[str, str]:
    """(layout, variant) from a map name: dd01_a -> (dd01, a); syn0001 -> (syn0001, "")."""
    match = NAME.match(stem)
    return (match.group(1), match.group(2)) if match else (stem, "")


def scan(raw: Path) -> list[tuple[str, Path]]:
    """(dataset, path) of every .dd2vtt directly in raw/<dataset>/; the demo map is "demo"."""
    found = []
    for dataset in DATASETS:
        for path in sorted((raw / dataset).glob("*.dd2vtt")):
            found.append(("demo" if path.stem == DEMO_MAP else dataset, path))
    return found


def read_manifest(path: Path) -> list[dict]:
    """The rows of an existing manifest, or [] if there is none."""
    if not path.exists():
        return []
    with open(path, newline="", encoding="utf-8") as f:
        return list(csv.DictReader(f))


def assign_splits(
    dataset: str, layouts: list[str], known: dict[str, str], seed: int
) -> dict[str, str]:
    """A split for every layout of one dataset, keeping the ones in `known`.

    New layouts are taken in an order shuffled by (seed, dataset). Each goes to the split
    whose count is furthest below its target share of all layouts; in real-map datasets an
    empty val or test split goes first once there are 3 or more layouts.
    """
    if dataset == "test":
        return {layout: "test" for layout in layouts}
    if dataset == "demo":
        return {layout: FIXTURE for layout in layouts}
    fractions = SPLITS[dataset]
    splits = {layout: known[layout] for layout in layouts if layout in known}
    new = sorted(layout for layout in layouts if layout not in known)
    random.Random(f"{seed}:{dataset}").shuffle(new)
    counts = Counter(splits.values())
    total = len(layouts)
    for layout in new:
        empty = [s for s in ("val", "test") if s in fractions and counts[s] == 0]
        if empty and total >= 3:
            split = empty[0]
        else:
            split = max(fractions, key=lambda s: fractions[s] * total - counts[s])
        splits[layout] = split
        counts[split] += 1
    return splits


def _fresh(outputs: list[Path], source: Path) -> bool:
    """True if every output exists and is newer than the source."""
    return all(p.exists() and p.stat().st_mtime >= source.stat().st_mtime for p in outputs)


def process_map(dataset: str, path: Path, processed: Path, force: bool = False) -> dict:
    """Rasterize one map at 70 and 32 px per square (unless fresh); return its manifest fields."""
    uvtt = load_uvtt(path)
    name = path.stem
    out, out32 = processed / dataset, processed / dataset / "32px"
    image, mask = out / f"{name}_image.jpg", out / f"{name}_mask.png"
    image32, mask32 = out32 / f"{name}_image.jpg", out32 / f"{name}_mask.png"
    preview = out / f"{name}_preview.jpg"
    if force or not _fresh([image, mask, preview, image32, mask32], path):
        rasterize_file(path, out)
        out32.mkdir(parents=True, exist_ok=True)
        decode_image(uvtt, TRAIN_PPG, Image.BOX).save(image32, quality=TRAIN_JPEG_QUALITY)
        Image.fromarray(rasterize_mask(uvtt, TRAIN_PPG)).save(mask32)

    shares = class_shares(np.array(Image.open(mask)))
    tiers = Counter(tier for _, _, tier in parse_lights(uvtt))
    size = uvtt["resolution"]["map_size"]
    return {
        "seed": uvtt.get("generator", {}).get("seed", ""),
        "width": size["x"],
        "height": size["y"],
        "source_ppg": uvtt["resolution"].get("pixels_per_grid", ""),
        **{f"share_{k}": f"{v:.5f}" for k, v in shares.items()},
        **{f"lights_{tier}": tiers[tier] for tier in LIGHT_TIERS},
        "image": image.relative_to(processed).as_posix(),
        "mask": mask.relative_to(processed).as_posix(),
        "image_32": image32.relative_to(processed).as_posix(),
        "mask_32": mask32.relative_to(processed).as_posix(),
    }


def build(raw: Path, processed: Path, seed: int = 42, force: bool = False) -> list[dict]:
    """Process every map, assign splits, write processed/manifest.csv; return the rows."""
    manifest = processed / "manifest.csv"
    known: dict[str, dict[str, str]] = defaultdict(dict)
    for row in read_manifest(manifest):
        known[row["dataset"]][row["layout"]] = row["split"]

    found = scan(raw)
    layouts: dict[str, list[str]] = defaultdict(list)
    for dataset, path in found:
        layout, _ = parse_name(path.stem)
        if layout not in layouts[dataset]:
            layouts[dataset].append(layout)
    splits = {
        dataset: assign_splits(dataset, names, known[dataset], seed)
        for dataset, names in layouts.items()
    }

    rows = []
    for dataset, path in found:
        layout, variant = parse_name(path.stem)
        row = {"dataset": dataset, "map": path.stem, "layout": layout, "variant": variant}
        row["split"] = splits[dataset][layout]
        row.update(process_map(dataset, path, processed, force))
        rows.append(row)

    processed.mkdir(parents=True, exist_ok=True)
    with open(manifest, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=COLUMNS)
        writer.writeheader()
        writer.writerows(rows)
    return rows


def main(argv: list[str] | None = None) -> None:
    """Command-line entry point: build the manifest and print maps per dataset and split."""
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--raw", type=Path, default=DATA / "raw")
    ap.add_argument("--processed", type=Path, default=DATA / "processed")
    ap.add_argument("--seed", type=int, default=42, help="split seed")
    ap.add_argument("--force", action="store_true", help="rasterize every map again")
    args = ap.parse_args(argv)

    rows = build(args.raw, args.processed, args.seed, args.force)
    counts = Counter((r["dataset"], r["split"]) for r in rows)
    layouts = defaultdict(set)
    for r in rows:
        layouts[(r["dataset"], r["split"])].add(r["layout"])
    for (dataset, split), n in sorted(counts.items()):
        print(f"{dataset:18} {split:8} {n:4} maps {len(layouts[(dataset, split)]):4} layouts")
    print(f"{len(rows)} maps -> {args.processed / 'manifest.csv'}")


if __name__ == "__main__":
    main()
