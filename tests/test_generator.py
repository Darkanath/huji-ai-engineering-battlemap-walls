"""Tests for data/generator.py and data/synth/: synthetic maps with exact labels."""

import copy
import json
from pathlib import Path

import numpy as np
import pytest

from data.generator import generate_map, load_config, main, next_index
from data.rasterize import (
    BACKGROUND,
    LIGHT,
    LIGHT_TIERS,
    PORTAL,
    WALL,
    class_shares,
    decode_image,
    load_uvtt,
    parse_lights,
    rasterize_mask,
)
from data.synth.layout import generate_layout


@pytest.fixture(scope="module")
def cfg() -> dict:
    """The shipped generator config."""
    return load_config()


@pytest.fixture(scope="module")
def small_cfg(cfg: dict) -> dict:
    """The shipped config on a 14x14-square map at 32 px per square, for fast tests."""
    small = copy.deepcopy(cfg)
    small["map_size"] = [14, 14]
    small["pixels_per_grid"] = 32
    return small


@pytest.fixture(scope="module")
def default_map(cfg: dict) -> tuple[dict, dict]:
    """One map at the default size and scale (25x25 squares, 70 px per square)."""
    return generate_map(cfg["seed"] + 1, cfg)


def test_same_seed_same_file(small_cfg: dict) -> None:
    """A map is fully determined by its seed; another seed gives another map."""
    a, _ = generate_map(7, small_cfg)
    b, _ = generate_map(7, small_cfg)
    c, _ = generate_map(8, small_cfg)
    assert json.dumps(a) == json.dumps(b)
    assert json.dumps(a) != json.dumps(c)


def test_output_is_a_valid_dd2vtt(default_map: tuple[dict, dict]) -> None:
    """The map has the Universal VTT fields, its seed, and an image of map_size x ppg."""
    uvtt, _ = default_map
    for key in ("resolution", "line_of_sight", "portals", "lights", "image"):
        assert key in uvtt
    assert uvtt["resolution"]["map_size"] == {"x": 25, "y": 25}
    assert decode_image(uvtt).size == (1750, 1750)
    assert "seed" in uvtt["generator"]


def test_mask_has_every_class(default_map: tuple[dict, dict]) -> None:
    """Walls, portals and lights are all labeled, with pixel shares in a sane range."""
    uvtt, _ = default_map
    mask = rasterize_mask(uvtt)
    assert set(np.unique(mask)) == {BACKGROUND, WALL, PORTAL, LIGHT}
    shares = class_shares(mask)
    assert 0.03 < shares["wall"] < 0.15
    assert 0.001 < shares["portal"] < 0.03
    assert 0.0005 < shares["light"] < 0.02


def test_gaps_stay_open(default_map: tuple[dict, dict]) -> None:
    """Every map has a doorless gap, and the mask has no wall in the middle of it."""
    uvtt, summary = default_map
    gaps = summary["openings"]["gap"]
    assert gaps
    mask = rasterize_mask(uvtt)
    ppg = uvtt["resolution"]["pixels_per_grid"]
    for (ax, ay), (bx, by) in gaps:
        x, y = (ax + bx) / 2 * ppg, (ay + by) / 2 * ppg
        assert mask[min(int(y), mask.shape[0] - 1), min(int(x), mask.shape[1] - 1)] != WALL


def test_lights_use_tier_ranges(default_map: tuple[dict, dict]) -> None:
    """Every light has a tier's range, so the rasterizer accepts it, and there are 3 or more."""
    uvtt, _ = default_map
    ranges = {t["range"] for t in LIGHT_TIERS.values()}
    assert all(light["range"] in ranges for light in uvtt["lights"])
    assert len(parse_lights(uvtt)) >= 3


@pytest.mark.parametrize("seed", range(30))
def test_every_room_is_reachable(cfg: dict, seed: int) -> None:
    """From any room or corridor cell, every other one can be reached through doors and gaps."""
    layout = generate_layout(np.random.default_rng(seed), 25, 25, cfg["layout"])
    regions, walls = layout.regions, layout.wall_edges
    inside = {(x, y) for y, x in zip(*np.nonzero(regions > 0), strict=True)}
    start = next(iter(sorted(inside)))
    seen, stack = {start}, [start]
    while stack:
        x, y = stack.pop()
        steps = [
            ((x + 1, y), ("v", x + 1, y)),
            ((x - 1, y), ("v", x, y)),
            ((x, y + 1), ("h", x, y + 1)),
            ((x, y - 1), ("h", x, y)),
        ]
        for cell, edge in steps:
            if cell in inside and cell not in seen and edge not in walls:
                seen.add(cell)
                stack.append(cell)
    assert seen == inside


def test_cli_numbers_files_after_existing(tmp_path: Path, cfg: dict) -> None:
    """The CLI writes synNNNN.dd2vtt after the highest existing number, with seed = base + N."""
    (tmp_path / "syn0003.dd2vtt").write_text("{}", encoding="utf-8")
    assert next_index(tmp_path) == 4
    main(["--count", "1", "--out", str(tmp_path)])
    uvtt = load_uvtt(tmp_path / "syn0004.dd2vtt")
    assert uvtt["generator"]["seed"] == cfg["seed"] + 4
