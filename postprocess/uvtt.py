"""Universal VTT (.dd2vtt) writer: an answer in grid squares -> the JSON Roll20 imports.

An answer is what the Claude tracer returns (llm/agent.py):

    {"walls":   [{"points": [{"x": 3, "y": 3}, {"x": 23, "y": 3}]}, ...],
     "arcs":    [{"cx": 3.5, "cy": 3.5, "r": 2.5, "start_deg": 10, "end_deg": 80}, ...],
     "portals": [{"x1": 5, "y1": 7, "x2": 6, "y2": 7}, ...],
     "lights":  [{"x": 11, "y": 18.5, "tier": "large"}, ...]}

All coordinates are grid squares with the origin at the map's top-left corner, y pointing down.
Walls are written exactly as given: the answer leaves the gap for each portal itself.
"""

import base64
import json
import math
from pathlib import Path

from data.rasterize import DEFAULT_PPG, LIGHT_TIERS

ARC_STEP_DEG = 5.0  # an arc becomes a polyline with a point about every 5 degrees
LIGHT_COLOR = "ffeccd8b"  # warm white, the color Dungeondraft exports for a torch
# What the file says for each light tier, unless the caller passes its own table (the app
# passes the one in llm/configs/claude.toml, which a test keeps equal to this).
DEFAULT_LIGHTS = {tier: {"range": v["range"], "intensity": 1} for tier, v in LIGHT_TIERS.items()}


def arc_points(cx: float, cy: float, r: float, start_deg: float, end_deg: float) -> list[dict]:
    """Points along a circular arc. Angles are measured from +x toward +y (clockwise on screen)."""
    n = max(2, round(abs(end_deg - start_deg) / ARC_STEP_DEG) + 1)
    out = []
    for i in range(n):
        t = math.radians(start_deg + (end_deg - start_deg) * i / (n - 1))
        out.append({"x": cx + r * math.cos(t), "y": cy + r * math.sin(t)})
    return out


def _portal(p: dict) -> dict:
    """One portal entry; Roll20 imports every portal as a door."""
    return {
        "position": {"x": (p["x1"] + p["x2"]) / 2, "y": (p["y1"] + p["y2"]) / 2},
        "bounds": [{"x": p["x1"], "y": p["y1"]}, {"x": p["x2"], "y": p["y2"]}],
        "rotation": math.atan2(p["y2"] - p["y1"], p["x2"] - p["x1"]),
        "closed": True,
        "freestanding": False,
    }


def _light(light: dict, lights: dict = DEFAULT_LIGHTS) -> dict:
    """One light entry; `range` and `intensity` come from the tier table, never the image."""
    spec = lights[light["tier"]]
    return {
        "position": {"x": light["x"], "y": light["y"]},
        "range": spec["range"],
        "intensity": spec["intensity"],
        "color": LIGHT_COLOR,
        "shadows": True,
    }


def answer_to_uvtt(
    answer: dict,
    map_size: tuple[int, int],
    ppg: int = DEFAULT_PPG,
    image_bytes: bytes | None = None,
    lights: dict = DEFAULT_LIGHTS,
) -> dict:
    """Build the .dd2vtt dict for a map of `map_size` squares.

    `image_bytes` is the encoded map image to embed (PNG or JPEG); without it the file has no
    image, which is enough for rasterizing and scoring. `lights` maps each tier to its
    `{"range", "intensity"}`.
    """
    lines = [
        [{"x": p["x"], "y": p["y"]} for p in w["points"]]
        for w in answer.get("walls", [])
        if len(w["points"]) >= 2
    ]
    lines += [
        arc_points(a["cx"], a["cy"], a["r"], a["start_deg"], a["end_deg"])
        for a in answer.get("arcs", [])
    ]
    return {
        "format": 0.3,
        "resolution": {
            "map_origin": {"x": 0, "y": 0},
            "map_size": {"x": map_size[0], "y": map_size[1]},
            "pixels_per_grid": ppg,
        },
        "line_of_sight": lines,
        "objects_line_of_sight": [],
        "portals": [_portal(p) for p in answer.get("portals", [])],
        "lights": [_light(light, lights) for light in answer.get("lights", [])],
        "environment": {"baked_lighting": True, "ambient_light": "ffffffff"},
        "image": base64.b64encode(image_bytes).decode("ascii") if image_bytes else "",
    }


def write_uvtt(path: str | Path, uvtt: dict) -> None:
    """Save the dict as a .dd2vtt file."""
    Path(path).write_text(json.dumps(uvtt))
