"""Thumbnail contact sheets, for checking datasets by eye and for the presentation.

`python -m data.contact_sheet` writes one sheet per dataset: a grid of every map's preview (the
image with walls, portals and lights tinted, written by data.manifest), each labeled with its
map name and split. `grid` is also used for the augmented-crop sheet (`python -m train.dataset`).

Usage:
  python -m data.contact_sheet [--datasets synthetic ...] [--thumb 200] [--cols 10]
                               [--out runs/sheets]
"""

import argparse
from collections import defaultdict
from pathlib import Path

from PIL import Image, ImageDraw

from data.manifest import read_manifest

ROOT = Path(__file__).parents[1]
LABEL_HEIGHT = 14
GAP = 4
BACKGROUND = (255, 255, 255)


def grid(images: list[Image.Image], cols: int, labels: list[str] | None = None) -> Image.Image:
    """Images of equal size in a grid of `cols` columns, each with an optional label below."""
    if not images:
        raise ValueError("no images for the grid")
    w, h = images[0].size
    label_h = LABEL_HEIGHT if labels else 0
    rows = -(-len(images) // cols)
    sheet = Image.new("RGB", (cols * (w + GAP) + GAP, rows * (h + label_h + GAP) + GAP), BACKGROUND)
    draw = ImageDraw.Draw(sheet)
    for i, image in enumerate(images):
        x = GAP + (i % cols) * (w + GAP)
        y = GAP + (i // cols) * (h + label_h + GAP)
        sheet.paste(image.convert("RGB"), (x, y))
        if labels:
            draw.text((x + 2, y + h + 1), labels[i], fill=(0, 0, 0))
    return sheet


def thumbnail(path: Path, size: int) -> Image.Image:
    """A `size`×`size` thumbnail of an image (aspect kept, padded with white)."""
    with Image.open(path) as image:
        image = image.convert("RGB")
        image.thumbnail((size, size), Image.BOX)
    tile = Image.new("RGB", (size, size), BACKGROUND)
    tile.paste(image, ((size - image.width) // 2, (size - image.height) // 2))
    return tile


def dataset_sheets(
    processed: Path, out_dir: Path, datasets: list[str] | None, thumb: int, cols: int
) -> list[Path]:
    """One sheet per dataset from the manifest's previews; returns the files written."""
    by_dataset: dict[str, list[dict]] = defaultdict(list)
    for row in read_manifest(processed / "manifest.csv"):
        if datasets is None or row["dataset"] in datasets:
            by_dataset[row["dataset"]].append(row)
    out_dir.mkdir(parents=True, exist_ok=True)
    written = []
    for dataset, rows in sorted(by_dataset.items()):
        previews = [processed / row["mask"].replace("_mask.png", "_preview.jpg") for row in rows]
        images = [thumbnail(p, thumb) for p in previews]
        labels = [f"{row['map']} ({row['split']})" for row in rows]
        path = out_dir / f"contact_sheet_{dataset}.jpg"
        grid(images, min(cols, len(images)), labels).save(path, quality=90)
        written.append(path)
    return written


def main(argv: list[str] | None = None) -> None:
    """Command-line entry point."""
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--processed", type=Path, default=ROOT / "data" / "processed")
    ap.add_argument("--datasets", nargs="+", help="default: every dataset in the manifest")
    ap.add_argument("--thumb", type=int, default=200, help="thumbnail size in px")
    ap.add_argument("--cols", type=int, default=10)
    ap.add_argument("--out", type=Path, default=ROOT / "runs" / "sheets")
    args = ap.parse_args(argv)

    for path in dataset_sheets(args.processed, args.out, args.datasets, args.thumb, args.cols):
        print(f"-> {path}")


if __name__ == "__main__":
    main()
