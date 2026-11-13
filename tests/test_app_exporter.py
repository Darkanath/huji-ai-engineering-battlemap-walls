"""The exported Universal VTT file: shape, scale, coordinates, lights and the golden file."""

import base64
import io
import json
import math

import pytest
from PIL import Image

from app.config import load_settings
from app.domain import Light, MapSize, Point, TraceResult, Usage, Wall
from app.exporter import build, write
from data.rasterize import load_uvtt

from conftest import FIXTURES


@pytest.fixture(scope="module")
def settings():
    """The shipped settings."""
    return load_settings()


@pytest.fixture
def image() -> Image.Image:
    """A small generated map image, 200 x 200 px."""
    img = Image.new("RGB", (200, 200), (120, 100, 80))
    img.paste((30, 30, 30), (20, 20, 180, 30))
    return img


def result(walls=(), lights=()) -> TraceResult:
    """A TraceResult with the given walls and lights and fixed bookkeeping."""
    return TraceResult(
        walls=list(walls),
        lights=list(lights),
        kind="quick",
        model_id="claude-sonnet-5-5",
        effort="medium",
        elapsed_s=1.0,
        usage=Usage(),
        cost_usd=0.0,
        traced_size=MapSize(width=10, height=10),
        size_source="typed",
    )


def decoded_size(payload: dict) -> tuple[int, int]:
    """The embedded image's size in pixels."""
    return Image.open(io.BytesIO(base64.b64decode(payload["image"]))).size


WALL = Wall(points=[Point(fx=0.2, fy=0.4), Point(fx=0.6, fy=0.4)])


def test_file_loads_with_scale_size_and_image(tmp_path, image, settings):
    """The file reads back; 70 px per square; the image is map size x 70 px."""
    size = MapSize(width=20, height=10)
    path = write(tmp_path / "m.dd2vtt", build(result([WALL]), size, image, settings))
    payload = load_uvtt(path)
    assert payload["resolution"]["pixels_per_grid"] == 70
    assert payload["resolution"]["map_size"] == {"x": 20, "y": 10}
    assert decoded_size(payload) == (1400, 700)


@pytest.mark.parametrize(
    ("width", "height", "expected"),
    [(20, 10, [(4, 4), (12, 4)]), (40, 20, [(8, 8), (24, 8)])],
)
def test_wall_coordinates_follow_the_map_size(image, settings, width, height, expected):
    """The same fractions land on the grid squares of the size given."""
    payload = build(result([WALL]), MapSize(width=width, height=height), image, settings)
    line = payload["line_of_sight"][0]
    assert [(p["x"], p["y"]) for p in line] == [pytest.approx(e) for e in expected]


def test_each_tier_writes_its_table_range_and_intensity(image, settings):
    """Lights get range and intensity from the config's tier table."""
    lights = [Light(at=Point(fx=0.5, fy=0.5), tier=t) for t in ("small", "medium", "large")]
    payload = build(result(lights=lights), MapSize(width=10, height=10), image, settings)
    for light, tier in zip(payload["lights"], ("small", "medium", "large"), strict=True):
        spec = settings.lights[tier]
        assert (light["range"], light["intensity"]) == (spec.range, spec.intensity)


def test_both_extensions_hold_identical_bytes(tmp_path, image, settings):
    """.dd2vtt and .uvtt of the same mask are the same bytes."""
    size = MapSize(width=10, height=10)
    a = write(tmp_path / "m.dd2vtt", build(result([WALL]), size, image, settings))
    b = write(tmp_path / "m.uvtt", build(result([WALL]), size, image, settings))
    assert a.read_bytes() == b.read_bytes()


def test_empty_mask_writes_empty_lists(tmp_path, image, settings):
    """A pass that found nothing still gives a valid file."""
    path = write(tmp_path / "m.uvtt", build(result(), MapSize(width=5, height=5), image, settings))
    payload = load_uvtt(path)
    assert payload["line_of_sight"] == payload["portals"] == payload["lights"] == []
    assert decoded_size(payload) == (350, 350)


def close(a, b) -> bool:
    """Deep equality of JSON values, with floats compared to 1e-9."""
    if isinstance(a, dict) and isinstance(b, dict):
        return a.keys() == b.keys() and all(close(a[k], b[k]) for k in a)
    if isinstance(a, list) and isinstance(b, list):
        return len(a) == len(b) and all(close(x, y) for x, y in zip(a, b, strict=True))
    if isinstance(a, int | float) and isinstance(b, int | float):
        return math.isclose(a, b, abs_tol=1e-9)
    return a == b


def test_golden_file(tmp_path, image, settings):
    """A fixed result and image give the committed file (image compared by decoded size)."""
    fixed = TraceResult.model_validate_json((FIXTURES / "golden_result.json").read_text())
    path = write(
        tmp_path / "golden.uvtt", build(fixed, MapSize(width=10, height=10), image, settings)
    )
    got = json.loads(path.read_text())
    want = json.loads((FIXTURES / "golden_export.uvtt").read_text())
    assert decoded_size(got) == (700, 700)
    got.pop("image"), want.pop("image")
    assert close(got, want)
