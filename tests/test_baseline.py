"""Tests for eval/baseline_canny.py: the Canny baseline and its tuning."""

from pathlib import Path

import numpy as np
import pytest

from data.rasterize import BACKGROUND, WALL, decode_image, load_uvtt, rasterize_mask
from eval.baseline_canny import grid_params, load_config, predict, tune, write_config

DEMO_MAP = Path(__file__).parents[1] / "data/raw/dungeondraft/demo-training-map.dd2vtt"
PPG = 32


@pytest.fixture(scope="module")
def demo() -> tuple[np.ndarray, np.ndarray]:
    """The demo map at 32 px per square: RGB image and true class mask."""
    uvtt = load_uvtt(DEMO_MAP)
    return np.array(decode_image(uvtt, PPG)), rasterize_mask(uvtt, PPG)


def test_predicts_a_wall_mask_of_the_right_shape(demo: tuple) -> None:
    """The baseline returns a mask of the image's size with only background and walls."""
    image, true = demo
    pred = predict(image, load_config()["params"], PPG)
    assert pred.shape == true.shape == (800, 800)
    assert set(np.unique(pred)) <= {BACKGROUND, WALL}
    assert (pred == WALL).any()


def test_tune_picks_a_grid_combination(demo: tuple) -> None:
    """Tuning returns one of the grid's combinations and its score."""
    grid = {"blur": [3, 5], "canny_low": [50], "high_ratio": [3], "close": [3], "min_length": [1.0]}
    params, f1 = tune([demo], grid, 0.25, PPG)
    assert params in grid_params(grid, 0.25)
    assert 0 < f1 <= 1


def test_write_config_round_trips(tmp_path: Path) -> None:
    """A written config loads back with the same params, grid and tuning note."""
    cfg = load_config()
    path = tmp_path / "canny.toml"
    tuned = {"on": "val: dd03_a", "boundary_f1_wall": 0.5, "date": "2026-10-21"}
    write_config(path, cfg["params"], cfg["grid"], tuned)
    again = load_config(path)
    assert again["params"] == cfg["params"]
    assert again["grid"] == cfg["grid"]
    assert again["tuned"] == tuned
