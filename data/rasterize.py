"""Turn a Universal VTT export (.dd2vtt / .uvtt / .df2vtt) into a training pair
for wall / portal segmentation: the map image and a class mask.

Classes: 0 background, 1 wall, 2 portal (doors and windows together;
the Universal VTT format does not say which portals are windows).

Usage:
  python -m data.rasterize MAP.dd2vtt [--ppg 70] [--out OUT_DIR]

Writes OUT_DIR/<name>_image.jpg, <name>_mask.png (class ids 0-2) and
<name>_preview.jpg (colored overlay for checking). Images are JPEG to save
space; the mask must stay PNG, because JPEG is lossy and would corrupt class ids.
The model itself only ever sees the image; the mask is the training label.
"""

import argparse
import base64
import io
import json
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw

BACKGROUND, WALL, PORTAL = 0, 1, 2
CLASS_NAMES = {BACKGROUND: "background", WALL: "wall", PORTAL: "portal"}
COLORS = {WALL: (255, 40, 40), PORTAL: (255, 0, 255)}
WALL_THICKNESS = 0.25  # in grid squares, matches Dungeondraft's default walls
PORTAL_THICKNESS = 0.30  # slightly thicker so portals win over the wall they sit in
DEFAULT_PPG = 70  # Roll20's default pixels per grid square
JPEG_QUALITY = 90  # demo map: 0.63 MB vs 1.68 MB as PNG

Image.MAX_IMAGE_PIXELS = None


def load_uvtt(path: str | Path) -> dict:
    """Read a Universal VTT JSON file."""
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def map_size_px(uvtt: dict, ppg: int = DEFAULT_PPG) -> tuple[int, int]:
    """Map size in pixels (width, height) at `ppg` pixels per grid square."""
    size = uvtt["resolution"]["map_size"]
    return round(size["x"] * ppg), round(size["y"] * ppg)


def decode_image(uvtt: dict, ppg: int = DEFAULT_PPG) -> Image.Image:
    """Decode the embedded map image and rescale it to `ppg` pixels per grid square.

    The embedded image is the source of truth, whatever its own `pixels_per_grid`.
    It may be PNG or JPEG; Pillow detects the format from the bytes.
    """
    image = Image.open(io.BytesIO(base64.b64decode(uvtt["image"]))).convert("RGB")
    size = map_size_px(uvtt, ppg)
    return image if image.size == size else image.resize(size, Image.LANCZOS)


def rasterize_mask(uvtt: dict, ppg: int = DEFAULT_PPG) -> np.ndarray:
    """Draw walls and portals into a uint8 class mask of shape (height, width).

    Walls are `line_of_sight` plus `objects_line_of_sight`; portals are drawn after
    the walls so they overwrite the wall segment they sit in.
    """
    origin = uvtt["resolution"]["map_origin"]
    ox, oy = origin["x"], origin["y"]

    def to_px(p: dict) -> tuple[float, float]:
        """Grid-square point {x, y} -> pixel (x, y), relative to the map origin."""
        return (p["x"] - ox) * ppg, (p["y"] - oy) * ppg

    mask = Image.new("L", map_size_px(uvtt, ppg), BACKGROUND)
    draw = ImageDraw.Draw(mask)

    wall_w = max(1, round(WALL_THICKNESS * ppg))
    for poly in uvtt.get("line_of_sight", []) + uvtt.get("objects_line_of_sight", []):
        draw.line([to_px(p) for p in poly], fill=WALL, width=wall_w, joint="curve")

    portal_w = max(1, round(PORTAL_THICKNESS * ppg))
    for portal in uvtt.get("portals", []):
        a, b = portal["bounds"]
        draw.line([to_px(a), to_px(b)], fill=PORTAL, width=portal_w)

    return np.array(mask)


def class_shares(mask: np.ndarray) -> dict[str, float]:
    """Fraction of pixels per class, keyed by class name."""
    return {name: float((mask == cls).mean()) for cls, name in CLASS_NAMES.items()}


def overlay(image: Image.Image, mask: np.ndarray) -> Image.Image:
    """Tint wall and portal pixels on top of the image, for visual checks."""
    preview = np.array(image).astype(np.float32)
    for cls, rgb in COLORS.items():
        sel = mask == cls
        preview[sel] = preview[sel] * 0.3 + np.array(rgb) * 0.7
    return Image.fromarray(preview.astype(np.uint8))


def rasterize_file(
    uvtt_path: str | Path, out_dir: str | Path = "out", ppg: int = DEFAULT_PPG
) -> dict[str, float]:
    """Write <name>_image.jpg, <name>_mask.png and <name>_preview.jpg; return class shares."""
    uvtt = load_uvtt(uvtt_path)
    image = decode_image(uvtt, ppg)
    mask = rasterize_mask(uvtt, ppg)

    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    name = Path(uvtt_path).stem
    image.save(out_dir / f"{name}_image.jpg", quality=JPEG_QUALITY)
    Image.fromarray(mask).save(out_dir / f"{name}_mask.png")  # lossless: keeps class ids exact
    overlay(image, mask).save(out_dir / f"{name}_preview.jpg", quality=JPEG_QUALITY)
    return class_shares(mask)


def main(argv: list[str] | None = None) -> None:
    """Command-line entry point."""
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("uvtt")
    ap.add_argument("--ppg", type=int, default=DEFAULT_PPG)
    ap.add_argument("--out", default="out")
    args = ap.parse_args(argv)

    shares = rasterize_file(args.uvtt, args.out, args.ppg)
    summary = ", ".join(f"{k} {v:.1%}" for k, v in shares.items())
    print(f"{Path(args.uvtt).stem}: {args.ppg} px/square, pixel share {summary}")


if __name__ == "__main__":
    main()
