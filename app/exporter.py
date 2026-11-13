"""The mask on screen -> a Universal VTT file (.dd2vtt / .uvtt) that Roll20 imports.

Coordinates are written in grid squares from the stored image fractions and the map size on
screen; the image is embedded at 70 px per square. The shape is defined in
`specs/001-battlemap-tracer-app/contracts/export-file.md`; the writing is done by
`postprocess.uvtt`, the writer that already produced a working Roll20 import.
"""

import io
from pathlib import Path

from PIL import Image

from app.config import Settings
from app.domain import MapSize, TraceResult, to_grid
from postprocess.uvtt import answer_to_uvtt, write_uvtt


def to_answer(result: TraceResult, map_size: MapSize) -> dict:
    """The result in grid squares on `map_size`, in the answer format `postprocess.uvtt` reads.

    Curves are already polylines, so there are no arcs.
    """

    def xy(point) -> dict:
        """One point in grid squares."""
        x, y = to_grid(point, map_size)
        return {"x": x, "y": y}

    portals = []
    for p in result.portals:
        a, b = xy(p.a), xy(p.b)
        portals.append({"x1": a["x"], "y1": a["y"], "x2": b["x"], "y2": b["y"]})
    return {
        "walls": [{"points": [xy(p) for p in w.points]} for w in result.walls],
        "arcs": [],
        "portals": portals,
        "lights": [{**xy(light.at), "tier": light.tier} for light in result.lights],
    }


def encode_image(image: Image.Image, map_size: MapSize, ppg: int, quality: int) -> bytes:
    """The map image resized to exactly `ppg` px per square and encoded as JPEG."""
    size = (map_size.width * ppg, map_size.height * ppg)
    resized = image if image.size == size else image.convert("RGB").resize(size, Image.LANCZOS)
    buf = io.BytesIO()
    resized.convert("RGB").save(buf, format="JPEG", quality=quality)
    return buf.getvalue()


def build(result: TraceResult, map_size: MapSize, image: Image.Image, settings: Settings) -> dict:
    """The Universal VTT dict for the result on `map_size`, with the image embedded."""
    ppg = settings.app.export_ppg
    image_bytes = encode_image(image, map_size, ppg, settings.app.export_jpeg_quality)
    return answer_to_uvtt(
        to_answer(result, map_size),
        map_size.as_tuple(),
        ppg,
        image_bytes,
        lights=settings.light_table(),
    )


def write(path: str | Path, payload: dict) -> Path:
    """Save the dict as JSON at `path` (the extension decides nothing: both are the same)."""
    write_uvtt(path, payload)
    return Path(path)
