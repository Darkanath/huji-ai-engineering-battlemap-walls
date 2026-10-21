"""The classical baseline (run R0): Canny edges and contours drawn as walls.

This is the approach existing auto-walling tools use, so it is the bar the U-Net has to clear.
On a map at `ppg` px per square:

    grayscale -> Gaussian blur -> Canny -> morphological close -> contours
    -> keep contours at least `min_length` squares long -> draw them as walls

Walls are drawn as wide as the label band (0.25 squares). The baseline predicts no portals and
no lights, so their scores are 0.

The parameters are in eval/configs/baseline_canny.toml. `--tune` grid-searches them on the
validation split, maximizing mean wall boundary F1, and writes the best values back to the
config with a note of what they were tuned on. After that the config is frozen: tuning again
needs `--retune`.

Usage:
  python -m eval.baseline_canny [--split val] [--datasets dungeondraft dungeon_alchemist] [--retune]
"""

import argparse
import itertools
import math
import tomllib
from datetime import date
from pathlib import Path

import cv2
import numpy as np

from data.rasterize import WALL
from eval.metrics import BOUNDARY_TOLERANCE, boundary_f1

CONFIG = Path(__file__).parent / "configs" / "baseline_canny.toml"
PARAM_KEYS = ("blur", "canny_low", "canny_high", "close", "min_length", "wall_width")


def load_config(path: Path = CONFIG) -> dict:
    """The baseline config: [params], the tuning [grid] and the [tuned] note."""
    with open(path, "rb") as f:
        return tomllib.load(f)


def predict(image: np.ndarray, params: dict, ppg: int) -> np.ndarray:
    """Class mask (0 background, 1 wall) predicted for an RGB image at `ppg` px per square."""
    gray = cv2.cvtColor(image, cv2.COLOR_RGB2GRAY)
    if params["blur"] > 1:
        gray = cv2.GaussianBlur(gray, (params["blur"], params["blur"]), 0)
    edges = cv2.Canny(gray, params["canny_low"], params["canny_high"])
    if params["close"] > 1:
        kernel = np.ones((params["close"], params["close"]), np.uint8)
        edges = cv2.morphologyEx(edges, cv2.MORPH_CLOSE, kernel)
    contours, _ = cv2.findContours(edges, cv2.RETR_LIST, cv2.CHAIN_APPROX_SIMPLE)
    keep = [c for c in contours if cv2.arcLength(c, False) >= params["min_length"] * ppg]
    mask = np.zeros(gray.shape, dtype=np.uint8)
    thickness = max(1, round(params["wall_width"] * ppg))
    cv2.drawContours(mask, keep, -1, int(WALL), thickness=thickness)
    return mask


def grid_params(grid: dict, wall_width: float) -> list[dict]:
    """Every parameter combination in the tuning grid (canny_high = canny_low x high_ratio)."""
    combos = []
    keys = ("blur", "canny_low", "high_ratio", "close", "min_length")
    for blur, low, ratio, close, length in itertools.product(*(grid[k] for k in keys)):
        combos.append(
            {
                "blur": blur,
                "canny_low": low,
                "canny_high": low * ratio,
                "close": close,
                "min_length": length,
                "wall_width": wall_width,
            }
        )
    return combos


def tune(
    maps: list[tuple[np.ndarray, np.ndarray]], grid: dict, wall_width: float, ppg: int
) -> tuple[dict, float]:
    """The grid parameters with the best mean wall boundary F1 on `maps` (image, true mask)."""
    best, best_f1 = None, -1.0
    for params in grid_params(grid, wall_width):
        scores = []
        for image, true in maps:
            f1 = boundary_f1(
                predict(image, params, ppg) == WALL, true == WALL, BOUNDARY_TOLERANCE * ppg
            )["f1"]
            if not math.isnan(f1):
                scores.append(f1)
        mean = sum(scores) / len(scores) if scores else 0.0
        if mean > best_f1:
            best, best_f1 = params, mean
    return best, best_f1


def _toml_value(value: object) -> str:
    """A number, string or list written as TOML."""
    if isinstance(value, str):
        return f'"{value}"'
    if isinstance(value, list):
        return "[" + ", ".join(_toml_value(v) for v in value) + "]"
    if isinstance(value, float) and math.isnan(value):
        return "nan"
    return str(value)


def write_config(path: Path, params: dict, grid: dict, tuned: dict) -> None:
    """Write the config back: the tuned params, the grid, and the note on the tuning run."""
    lines = [
        "# Canny baseline (run R0, eval/baseline_canny.py). [params] are what the baseline uses;",
        "# `python -m eval.baseline_canny` overwrites them with the best values from [grid]",
        "# on the validation split and records the run in [tuned]. Frozen once tuned.",
        "",
        "[params]",
        *(f"{k} = {_toml_value(params[k])}" for k in PARAM_KEYS),
        "",
        "[grid]  # tuning grid; canny_high = canny_low x high_ratio",
        *(f"{k} = {_toml_value(v)}" for k, v in grid.items()),
        "",
        "[tuned]",
        *(f"{k} = {_toml_value(v)}" for k, v in tuned.items()),
        "",
    ]
    path.write_text("\n".join(lines), encoding="utf-8")


def main(argv: list[str] | None = None) -> None:
    """Command-line entry point: tune the baseline on a split and write the config."""
    from eval.evaluate import DEFAULT_MANIFEST, load_maps, select_rows

    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--retune", action="store_true", help="overwrite an earlier tuning")
    ap.add_argument("--split", default="val")
    ap.add_argument("--datasets", nargs="+", default=["dungeondraft", "dungeon_alchemist"])
    ap.add_argument("--manifest", type=Path, default=DEFAULT_MANIFEST)
    ap.add_argument("--config", type=Path, default=CONFIG)
    args = ap.parse_args(argv)

    cfg = load_config(args.config)
    if cfg["tuned"]["date"] and not args.retune:
        raise SystemExit(f"already tuned on {cfg['tuned']['date']}; pass --retune to tune again")
    rows = select_rows(args.manifest, args.split, args.datasets)
    if not rows:
        raise SystemExit(f"no {args.split} maps in {args.datasets}")
    maps = [(image, true) for _, image, true in load_maps(args.manifest.parent, rows)]
    ppg = 32
    params, f1 = tune(maps, cfg["grid"], cfg["params"]["wall_width"], ppg)
    tuned = {
        "on": f"{args.split} of {', '.join(args.datasets)}: {', '.join(r['map'] for r in rows)}",
        "boundary_f1_wall": round(f1, 4),
        "date": date.today().isoformat(),
    }
    write_config(args.config, params, cfg["grid"], tuned)
    print(f"best wall boundary F1 {f1:.3f} with {params}")
    print(f"tuned on {len(rows)} maps; written to {args.config}")


if __name__ == "__main__":
    main()
