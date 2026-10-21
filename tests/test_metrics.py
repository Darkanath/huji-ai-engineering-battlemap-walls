"""Tests for eval/metrics.py: pixel IoU and F1, wall boundary F1, means."""

import math

import numpy as np
import pytest

from data.rasterize import BACKGROUND, LIGHT, PORTAL, WALL
from eval.metrics import boundary_f1, iou_f1, mean_scores, score

PPG = 32


@pytest.fixture
def truth() -> np.ndarray:
    """A 128x128 mask: an 8 px wall across the middle with a portal in it, and a light."""
    mask = np.full((128, 128), BACKGROUND, dtype=np.uint8)
    mask[60:68, :] = WALL
    mask[59:69, 40:72] = PORTAL
    mask[20:30, 100:110] = LIGHT
    return mask


def test_perfect_prediction_scores_one(truth: np.ndarray) -> None:
    """Predicting the ground truth gives 1 on every metric."""
    scores = score(truth, truth, PPG)
    assert all(v == pytest.approx(1.0) for v in scores.values())


def test_empty_prediction_scores_zero(truth: np.ndarray) -> None:
    """Predicting only background gives 0 for every class that is in the ground truth."""
    scores = score(np.zeros_like(truth), truth, PPG)
    for key in ("iou_wall", "f1_wall", "iou_portal", "iou_light", "boundary_f1_wall"):
        assert scores[key] == 0


def test_small_shift_keeps_boundary_f1_high(truth: np.ndarray) -> None:
    """A wall predicted 2 px off loses pixel IoU but keeps boundary F1 near 1."""
    shifted = np.roll(truth, 2, axis=0)
    scores = score(shifted, truth, PPG)
    assert scores["iou_wall"] < 0.8
    assert scores["boundary_f1_wall"] > 0.95


def test_far_wall_scores_low_boundary_f1(truth: np.ndarray) -> None:
    """A wall predicted 20 px away (far past the 3 px tolerance) is not found."""
    shifted = np.roll(truth, 20, axis=0)
    assert score(shifted, truth, PPG)["boundary_f1_wall"] < 0.1


def test_absent_class_is_nan_and_skipped_in_means() -> None:
    """A class in neither mask has no score, and the mean ignores it."""
    empty = np.zeros((10, 10), dtype=bool)
    assert all(math.isnan(v) for v in iou_f1(empty, empty))
    assert math.isnan(boundary_f1(empty, empty, 3)["f1"])
    means = mean_scores([{"iou_portal": 0.5}, {"iou_portal": math.nan}])
    assert means["iou_portal"] == 0.5


def test_shape_mismatch_raises(truth: np.ndarray) -> None:
    """Masks of different sizes are an error, not a silent broadcast."""
    with pytest.raises(ValueError, match="differ in shape"):
        score(truth[:64], truth, PPG)
