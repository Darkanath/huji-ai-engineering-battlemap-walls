"""Rewrite the lights of a .dd2vtt exported by another map tool to the project's light tiers.

Tools like Dungeon Alchemist set each light's `range` by asset type, not by the project's
tier ranges (data/rasterize.py, LIGHT_TIERS), so the rasterizer would reject them. This
script matches each light to a rule in data/configs/light_sources.toml by its exported
`range` and `intensity`, sets `range` to its tier's value, and drops lights the rules mark
as "drop". Everything else in the file is copied unchanged.

The original export is never modified: originals stay in `<dataset>/original/` and the
converted file is written to the dataset folder, so a conversion can always be redone.

Usage:
  python -m data.retier_lights --source dungeon_alchemist \\
      data/raw/dungeon_alchemist/original/da01_a.dd2vtt --out data/raw/dungeon_alchemist
"""

import argparse
import json
import tomllib
from collections import Counter
from pathlib import Path

from data.rasterize import LIGHT_TIERS, load_uvtt

DEFAULT_CONFIG = Path(__file__).parent / "configs" / "light_sources.toml"
RANGE_TOLERANCE = 0.01  # grid squares
INTENSITY_TOLERANCE = 0.02
DROP = "drop"


def load_rules(source: str, config: str | Path = DEFAULT_CONFIG) -> list[dict]:
    """The light rules for one source tool, checked to name a known tier or "drop"."""
    with open(config, "rb") as f:
        rules = tomllib.load(f)[source]["rules"]
    for rule in rules:
        if rule["tier"] not in LIGHT_TIERS and rule["tier"] != DROP:
            raise ValueError(f"rule {rule} has unknown tier {rule['tier']!r}")
    return rules


def match_rule(light: dict, rules: list[dict]) -> dict | None:
    """The rule whose range and intensity match the light, or None."""
    for rule in rules:
        if (
            abs(light["range"] - rule["range"]) <= RANGE_TOLERANCE
            and abs(light["intensity"] - rule["intensity"]) <= INTENSITY_TOLERANCE
        ):
            return rule
    return None


def retier(uvtt: dict, rules: list[dict]) -> tuple[dict, Counter]:
    """Return a copy of `uvtt` with lights rewritten to tier ranges, and a count per rule.

    Raises ValueError listing every unmatched light (range, intensity, position), so all
    new asset types in a map can be added to the config in one go.
    """
    lights, counts, unknown = [], Counter(), []
    for light in uvtt.get("lights", []):
        rule = match_rule(light, rules)
        if rule is None:
            pos = light["position"]
            unknown.append(
                f"range {light['range']:g}, intensity {light['intensity']:g} "
                f"at ({pos['x']:.2f}, {pos['y']:.2f})"
            )
            continue
        counts[f"{rule['what']} -> {rule['tier']}"] += 1
        if rule["tier"] != DROP:
            lights.append({**light, "range": LIGHT_TIERS[rule["tier"]]["range"]})
    if unknown:
        raise ValueError("lights match no rule:\n  " + "\n  ".join(unknown))
    return {**uvtt, "lights": lights}, counts


def retier_file(path: str | Path, out_dir: str | Path, rules: list[dict]) -> tuple[Path, Counter]:
    """Convert one file into `out_dir` under the same name; return the output path and counts."""
    path, out_dir = Path(path), Path(out_dir)
    if path.parent.resolve() == out_dir.resolve():
        raise ValueError(f"{path} would overwrite itself; keep originals in a separate folder")
    uvtt, counts = retier(load_uvtt(path), rules)
    out_dir.mkdir(parents=True, exist_ok=True)
    out = out_dir / path.name
    out.write_text(json.dumps(uvtt), encoding="utf-8")
    return out, counts


def main(argv: list[str] | None = None) -> None:
    """Command-line entry point."""
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("uvtt", nargs="+")
    ap.add_argument("--source", required=True, help="section of the config, e.g. dungeon_alchemist")
    ap.add_argument("--out", required=True, help="dataset folder to write the converted files to")
    ap.add_argument("--config", default=DEFAULT_CONFIG)
    args = ap.parse_args(argv)

    rules = load_rules(args.source, args.config)
    for path in args.uvtt:
        out, counts = retier_file(path, args.out, rules)
        summary = ", ".join(f"{n} {what}" for what, n in sorted(counts.items()))
        print(f"{out}: {summary or 'no lights'}")


if __name__ == "__main__":
    main()
