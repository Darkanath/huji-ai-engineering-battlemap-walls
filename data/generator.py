"""Generate synthetic battlemaps with exact labels, saved as Universal VTT (.dd2vtt) files.

Each map is a random layout of rooms and corridors (data/synth/layout.py), dressed with
furniture, light sources and unlit fixtures (data/synth/dress.py) and drawn with procedural
textures and image effects (data/synth/render.py). The generator decides where every wall,
portal and light goes, so the .dd2vtt it writes is an exact label; the rasterizer turns it into
a mask like any other map.

Map number i is generated from seed `config seed + i` and written as
`data/raw/synthetic/syn<iiii>.dd2vtt` with the image embedded as PNG. The seed and generator
version are stored in the file under "generator".

Usage:
  python -m data.generator --count 20 [--start 1] [--out data/raw/synthetic]
"""

import argparse
import base64
import io
import json
import math
import re
import time
import tomllib
from pathlib import Path

import numpy as np
from PIL import Image

from data.synth.dress import dress
from data.synth.layout import Layout, Opening, generate_layout
from data.synth.render import render

DEFAULT_CONFIG = Path(__file__).parent / "configs" / "generator.toml"
DEFAULT_OUT = Path(__file__).parent / "raw" / "synthetic"
GENERATOR_VERSION = 1
NAME = re.compile(r"syn(\d{4,})\.dd2vtt$")


def load_config(path: str | Path = DEFAULT_CONFIG) -> dict:
    """Read the generator's TOML config."""
    with open(path, "rb") as f:
        return tomllib.load(f)


def portal(opening: Opening) -> dict:
    """A .dd2vtt portal for a door (closed) or window (open)."""
    (ax, ay), (bx, by) = opening.endpoints()
    return {
        "position": {"x": (ax + bx) / 2, "y": (ay + by) / 2},
        "bounds": [{"x": ax, "y": ay}, {"x": bx, "y": by}],
        "rotation": 0.0 if opening.orient == "h" else math.pi / 2,
        "closed": opening.kind == "door",
        "freestanding": False,
    }


def encode_png(image: Image.Image) -> str:
    """The image as a base64 PNG string."""
    buf = io.BytesIO()
    image.save(buf, format="PNG")
    return base64.b64encode(buf.getvalue()).decode("ascii")


def to_uvtt(
    layout: Layout, lights: list[dict], image: Image.Image, ppg: int, baked: bool, seed: int
) -> dict:
    """Assemble the .dd2vtt dict: walls, portals (doors and windows), lights, image."""
    return {
        "format": 0.3,
        "resolution": {
            "map_origin": {"x": 0, "y": 0},
            "map_size": {"x": layout.width, "y": layout.height},
            "pixels_per_grid": ppg,
        },
        "line_of_sight": [[{"x": x, "y": y} for x, y in poly] for poly in layout.walls],
        "objects_line_of_sight": [],
        "portals": [portal(o) for o in layout.openings if o.kind != "gap"],
        "environment": {"baked_lighting": baked, "ambient_light": "ffffffff"},
        "lights": lights,
        "image": encode_png(image),
        "generator": {"version": GENERATOR_VERSION, "seed": seed},
    }


def generate_map(seed: int, cfg: dict) -> tuple[dict, dict]:
    """One synthetic map from `seed`: its .dd2vtt dict and a summary for checks and logs.

    The summary lists the layout style, the openings by kind (gaps included, which the .dd2vtt
    does not record) and the image effects applied.
    """
    rng = np.random.default_rng(seed)
    width, height = cfg["map_size"]
    ppg = cfg["pixels_per_grid"]
    layout = generate_layout(rng, width, height, cfg["layout"])
    items, lights = dress(rng, layout, cfg)
    image, effects = render(rng, layout, items, cfg, ppg)
    uvtt = to_uvtt(layout, lights, image, ppg, effects["glow"], seed)
    summary = {
        "style": layout.style,
        "openings": {
            kind: [o.endpoints() for o in layout.openings if o.kind == kind]
            for kind in ("door", "window", "gap")
        },
        "lights": len(lights),
        "effects": effects,
    }
    return uvtt, summary


def next_index(out_dir: Path) -> int:
    """The number after the highest synNNNN.dd2vtt in `out_dir` (1 if there is none)."""
    numbers = [int(m.group(1)) for p in out_dir.glob("syn*.dd2vtt") if (m := NAME.match(p.name))]
    return max(numbers, default=0) + 1


def main(argv: list[str] | None = None) -> None:
    """Command-line entry point."""
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--count", type=int, default=1)
    ap.add_argument("--start", type=int, help="first map number (default: after the last one)")
    ap.add_argument("--out", type=Path, default=DEFAULT_OUT)
    ap.add_argument("--config", type=Path, default=DEFAULT_CONFIG)
    args = ap.parse_args(argv)

    cfg = load_config(args.config)
    args.out.mkdir(parents=True, exist_ok=True)
    start = args.start if args.start is not None else next_index(args.out)
    for index in range(start, start + args.count):
        t0 = time.perf_counter()
        uvtt, summary = generate_map(cfg["seed"] + index, cfg)
        path = args.out / f"syn{index:04d}.dd2vtt"
        path.write_text(json.dumps(uvtt), encoding="utf-8")
        n = {kind: len(v) for kind, v in summary["openings"].items()}
        effects = ",".join(k for k, v in summary["effects"].items() if v) or "none"
        print(
            f"{path.name}: {summary['style']}, {len(uvtt['line_of_sight'])} walls, "
            f"{n['door']} doors, {n['window']} windows, {n['gap']} gaps, "
            f"{summary['lights']} lights, effects {effects}, "
            f"{path.stat().st_size / 1e6:.1f} MB, {time.perf_counter() - t0:.1f} s"
        )


if __name__ == "__main__":
    main()
