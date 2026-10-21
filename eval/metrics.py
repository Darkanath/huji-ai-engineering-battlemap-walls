"""Segmentation metrics: pixel IoU and F1 per class, and wall boundary F1 with a tolerance.

All functions take class masks (uint8 arrays of class ids, docs/labeling-rules.md) of the same
shape: a prediction and the ground truth.

- **Pixel IoU / F1** per class: overlap of predicted and true pixels of that class.
- **Wall boundary F1:** walls are thin, so a wall predicted 2 px off is not wrong. A predicted
  wall pixel counts as correct if a true wall pixel is within `tolerance` px, and a true wall
  pixel counts as found if a predicted one is within `tolerance` px; F1 combines the two.
  The default tolerance is 0.1 square (3 px at 32 px per square, docs/training.md).

A class absent from both masks has no defined score (NaN); `mean_scores` skips NaN, so a map
without portals doesn't count as a perfect portal score.
"""

import math

import cv2
import numpy as np

from data.rasterize import LIGHT, PORTAL, WALL

SCORED = {WALL: "wall", PORTAL: "portal", LIGHT: "light"}  # background is not scored
BOUNDARY_TOLERANCE = 0.1  # squares


def iou_f1(pred: np.ndarray, true: np.ndarray) -> tuple[float, float]:
    """IoU and F1 of two boolean masks; (nan, nan) if both are empty."""
    tp = int(np.count_nonzero(pred & true))
    fp = int(np.count_nonzero(pred & ~true))
    fn = int(np.count_nonzero(~pred & true))
    if tp + fp + fn == 0:
        return math.nan, math.nan
    return tp / (tp + fp + fn), 2 * tp / (2 * tp + fp + fn)


def _distance_to(mask: np.ndarray) -> np.ndarray:
    """Distance in px from every pixel to the nearest True pixel of `mask` (inf if none)."""
    if not mask.any():
        return np.full(mask.shape, np.inf, dtype=np.float32)
    return cv2.distanceTransform((~mask).astype(np.uint8), cv2.DIST_L2, 5)


def boundary_f1(pred: np.ndarray, true: np.ndarray, tolerance: float) -> dict[str, float]:
    """Precision, recall and F1 of two boolean masks with a distance tolerance in px.

    Both empty -> all nan; one empty -> 0.
    """
    if not pred.any() and not true.any():
        return {"precision": math.nan, "recall": math.nan, "f1": math.nan}
    precision = float((_distance_to(true)[pred] <= tolerance).mean()) if pred.any() else 0.0
    recall = float((_distance_to(pred)[true] <= tolerance).mean()) if true.any() else 0.0
    f1 = 2 * precision * recall / (precision + recall) if precision + recall else 0.0
    return {"precision": precision, "recall": recall, "f1": f1}


def score(pred: np.ndarray, true: np.ndarray, ppg: int) -> dict[str, float]:
    """All metrics for one map at `ppg` px per square, as a flat dict.

    Keys: iou_<class>, f1_<class> for wall, portal and light; boundary_precision_wall,
    boundary_recall_wall and boundary_f1_wall.
    """
    if pred.shape != true.shape:
        raise ValueError(f"prediction {pred.shape} and ground truth {true.shape} differ in shape")
    out = {}
    for cls, name in SCORED.items():
        out[f"iou_{name}"], out[f"f1_{name}"] = iou_f1(pred == cls, true == cls)
    boundary = boundary_f1(pred == WALL, true == WALL, BOUNDARY_TOLERANCE * ppg)
    out.update({f"boundary_{k}_wall": v for k, v in boundary.items()})
    return out


def mean_scores(rows: list[dict[str, float]]) -> dict[str, float]:
    """The mean of each metric over maps, skipping NaN (nan if a metric is NaN everywhere)."""
    keys = [k for k in rows[0] if isinstance(rows[0][k], float)] if rows else []
    out = {}
    for key in keys:
        values = [r[key] for r in rows if not math.isnan(r[key])]
        out[key] = sum(values) / len(values) if values else math.nan
    return out
