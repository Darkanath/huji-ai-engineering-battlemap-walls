"""Tests for data/rasterize.py: the .dd2vtt -> class mask rasterizer."""

import base64
import io
import json
from pathlib import Path

import numpy as np
import pytest
from PIL import Image

from data.rasterize import (
    BACKGROUND,
    PORTAL,
    WALL,
    class_shares,
    decode_image,
    load_uvtt,
    main,
    rasterize_mask,
)

DEMO_MAP = Path(__file__).parents[1] / "data/raw/dungeondraft/demo-training-map.dd2vtt"


@pytest.fixture(scope="module")
def demo_uvtt() -> dict:
    """The demo Dungeondraft export (25x25 squares, 70 px/square), loaded once."""
    return load_uvtt(DEMO_MAP)


@pytest.fixture(scope="module")
def demo_mask(demo_uvtt: dict) -> np.ndarray:
    """Class mask of the demo map at the default 70 px/square."""
    return rasterize_mask(demo_uvtt)


def make_uvtt(image_ppg: int = 20, image_format: str = "PNG") -> dict:
    """A 4x4-square map with origin (1, 1): one horizontal wall with a portal in it.

    `image_format` sets how the embedded image is encoded (PNG or JPEG).
    """
    image = Image.new("RGB", (4 * image_ppg, 4 * image_ppg), (200, 180, 150))
    buf = io.BytesIO()
    image.save(buf, format=image_format)
    return {
        "format": 0.3,
        "resolution": {
            "map_origin": {"x": 1, "y": 1},
            "map_size": {"x": 4, "y": 4},
            "pixels_per_grid": image_ppg,
        },
        "line_of_sight": [[{"x": 1, "y": 3}, {"x": 5, "y": 3}]],
        "portals": [{"bounds": [{"x": 2, "y": 3}, {"x": 3, "y": 3}]}],
        "image": base64.b64encode(buf.getvalue()).decode(),
    }


# --- demo map ---------------------------------------------------------------


def test_demo_mask_has_only_known_classes(demo_mask: np.ndarray) -> None:
    """The mask is uint8 and uses only class ids 0 (background), 1 (wall), 2 (portal)."""
    assert demo_mask.dtype == np.uint8
    assert set(np.unique(demo_mask)) <= {BACKGROUND, WALL, PORTAL}


def test_demo_mask_matches_image_size(demo_uvtt: dict, demo_mask: np.ndarray) -> None:
    """Mask and decoded image align pixel for pixel, at map_size x 70 px."""
    image = decode_image(demo_uvtt)
    assert demo_mask.shape == (1750, 1750)  # 25 x 25 squares at 70 px
    assert image.size == demo_mask.shape[::-1]


def test_demo_class_shares(demo_mask: np.ndarray) -> None:
    """Walls cover about 7% of the demo map and portals under 2%, as measured in PLAN.md."""
    shares = class_shares(demo_mask)
    assert 0.05 < shares["wall"] < 0.09  # about 7%
    assert 0 < shares["portal"] < 0.02  # under 1-2%
    assert sum(shares.values()) == pytest.approx(1.0)


# --- small hand-made map ----------------------------------------------------


def test_wall_and_portal_land_on_expected_pixels() -> None:
    """Grid coordinates map to the right pixels, honoring a non-zero map origin,
    and a portal overwrites the wall it sits in."""
    mask = rasterize_mask(make_uvtt(), ppg=10)
    assert mask.shape == (40, 40)
    # Grid y=3 with origin y=1 -> pixel row 20.
    assert mask[20, 35] == WALL
    assert mask[20, 15] == PORTAL  # portal from x=2..3 -> px 10..20, drawn over the wall
    assert mask[5, 5] == BACKGROUND
    assert mask[35, 35] == BACKGROUND


def test_decode_rescales_any_source_ppg() -> None:
    """The embedded image is rescaled to the requested px/square, whatever its own scale."""
    assert decode_image(make_uvtt(image_ppg=20), ppg=10).size == (40, 40)
    assert decode_image(make_uvtt(image_ppg=7), ppg=32).size == (128, 128)


def test_decode_accepts_embedded_jpeg() -> None:
    """A .dd2vtt whose embedded image is JPEG decodes like a PNG one."""
    image = decode_image(make_uvtt(image_format="JPEG"), ppg=10)
    assert image.size == (40, 40)
    assert image.mode == "RGB"


def test_cli_writes_outputs(tmp_path: Path, capsys: pytest.CaptureFixture) -> None:
    """The CLI writes a JPEG image and preview and a PNG mask that keeps exact class ids."""
    src = tmp_path / "tiny.dd2vtt"
    src.write_text(json.dumps(make_uvtt()), encoding="utf-8")
    main([str(src), "--ppg", "10", "--out", str(tmp_path / "out")])

    for filename in ("tiny_image.jpg", "tiny_mask.png", "tiny_preview.jpg"):
        assert (tmp_path / "out" / filename).exists()
    assert Image.open(tmp_path / "out" / "tiny_image.jpg").format == "JPEG"
    saved = np.array(Image.open(tmp_path / "out" / "tiny_mask.png"))
    assert set(np.unique(saved)) == {BACKGROUND, WALL, PORTAL}
    assert "wall" in capsys.readouterr().out
