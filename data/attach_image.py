"""Swap the original test image into a hand-traced .dd2vtt (docs/labeling-rules.md).

A test map is traced in Dungeondraft over the original image, but the export embeds
Dungeondraft's own rendering. This replaces the embedded image with the original one and sets
`resolution.pixels_per_grid` from its size, so the labels sit on the image the model is tested
on. The image bytes are embedded as they are (JPEG, PNG or WebP), without re-encoding.

The image must be exactly `map_size` squares at a whole number of px per square, the same in
both directions; anything else means it was not cropped to the grid, and is refused.

Usage:
  python -m data.attach_image data/raw/test/tNN.dd2vtt data/raw/test/tNN.jpg [--out OUT.dd2vtt]
"""

import argparse
import base64
import io
import json
from pathlib import Path

from PIL import Image

from data.rasterize import load_uvtt


def pixels_per_grid(image_size: tuple[int, int], map_size: dict) -> int:
    """Px per square of an image covering `map_size` squares; ValueError if it doesn't fit."""
    width, height = image_size
    squares_x, squares_y = map_size["x"], map_size["y"]
    ppg = width / squares_x
    if ppg != int(ppg) or height != ppg * squares_y:
        raise ValueError(
            f"image is {width}x{height} px, which is not {squares_x:g}x{squares_y:g} squares "
            "at a whole number of px per square; crop it to the grid first"
        )
    return int(ppg)


def attach_image(uvtt: dict, image_bytes: bytes) -> dict:
    """A copy of `uvtt` with `image_bytes` embedded and `pixels_per_grid` set to match."""
    with Image.open(io.BytesIO(image_bytes)) as image:
        size = image.size
    ppg = pixels_per_grid(size, uvtt["resolution"]["map_size"])
    out = {**uvtt, "resolution": {**uvtt["resolution"], "pixels_per_grid": ppg}}
    out["image"] = base64.b64encode(image_bytes).decode("ascii")
    return out


def main(argv: list[str] | None = None) -> None:
    """Command-line entry point: embed the image, write the .dd2vtt (in place by default)."""
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("uvtt", type=Path, help="the hand-traced .dd2vtt export")
    ap.add_argument("image", type=Path, help="the original test image (.jpg, .png or .webp)")
    ap.add_argument("--out", type=Path, help="output .dd2vtt (default: overwrite the input)")
    args = ap.parse_args(argv)

    try:
        uvtt = attach_image(load_uvtt(args.uvtt), args.image.read_bytes())
    except ValueError as err:
        raise SystemExit(f"{args.image}: {err}") from err
    out = args.out or args.uvtt
    out.write_text(json.dumps(uvtt), encoding="utf-8")
    ppg = uvtt["resolution"]["pixels_per_grid"]
    print(f"{args.image.name} -> {out} ({ppg} px per square)")


if __name__ == "__main__":
    main()
