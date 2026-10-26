"""Training loss: weighted cross-entropy + soft Dice (docs/training.md §4).

- **Class weights:** `w_c = 1 / sqrt(share_c)`, normalized so background is 1 and capped (20 by
  default). The shares are the pixel shares of the current stage's training split, read from the
  manifest, so a class that is rare in the data (portals, lights) gets a larger weight.
- **Dice:** soft multi-class Dice on the softmax, averaged over wall, portal and light.
  Background is left out: its Dice is always near 1 and adds nothing.

The loss works on logits during training and on averaged probabilities during validation
(whole maps are predicted with overlapping windows whose probabilities are averaged).
"""

import math

import torch
import torch.nn.functional as F
from torch import nn

from data.rasterize import BACKGROUND, CLASS_NAMES

EPS = 1e-6
DICE_SMOOTH = 1.0


def split_shares(rows: list[dict]) -> list[float]:
    """Pixel share of each class over a set of manifest rows, weighting maps by their area."""
    total = [0.0] * len(CLASS_NAMES)
    area_sum = 0.0
    for row in rows:
        area = float(row["width"]) * float(row["height"])
        area_sum += area
        for cls, name in CLASS_NAMES.items():
            total[cls] += float(row[f"share_{name}"]) * area
    if area_sum == 0:
        raise ValueError("no maps to compute class shares from")
    return [t / area_sum for t in total]


def class_weights(shares: list[float], cap: float = 20.0) -> list[float]:
    """Weights 1/sqrt(share), relative to background, capped at `cap`.

    A class with no pixels at all (e.g. no lights in the split) gets the cap.
    """
    raw = [1 / math.sqrt(s) if s > 0 else math.inf for s in shares]
    return [min(w / raw[BACKGROUND], cap) for w in raw]


def soft_dice(probs: torch.Tensor, target: torch.Tensor, classes: list[int]) -> torch.Tensor:
    """Mean soft Dice loss (1 - Dice) over `classes`, from probabilities (N, C, H, W) and class
    ids (N, H, W). A class absent from both scores near 0 loss thanks to the smoothing term."""
    one_hot = F.one_hot(target, probs.shape[1]).permute(0, 3, 1, 2).to(probs.dtype)
    losses = []
    for cls in classes:
        p, t = probs[:, cls], one_hot[:, cls]
        dice = (2 * (p * t).sum() + DICE_SMOOTH) / (p.sum() + t.sum() + DICE_SMOOTH)
        losses.append(1 - dice)
    return torch.stack(losses).mean()


class SegLoss(nn.Module):
    """`ce_weight * weighted CE + dice_weight * Dice` over the non-background classes."""

    def __init__(self, weights: list[float], ce_weight: float = 1.0, dice_weight: float = 1.0):
        super().__init__()
        self.register_buffer("weights", torch.tensor(weights, dtype=torch.float32))
        self.ce_weight = ce_weight
        self.dice_weight = dice_weight
        self.dice_classes = [c for c in CLASS_NAMES if c != BACKGROUND]

    def forward(self, logits: torch.Tensor, target: torch.Tensor) -> torch.Tensor:
        """Loss from logits (N, C, H, W) and class ids (N, H, W); computed in float32."""
        logits = logits.float()
        ce = F.cross_entropy(logits, target, weight=self.weights)
        dice = soft_dice(logits.softmax(dim=1), target, self.dice_classes)
        return self.ce_weight * ce + self.dice_weight * dice

    def from_probs(self, probs: torch.Tensor, target: torch.Tensor) -> torch.Tensor:
        """The same loss from probabilities (N, C, H, W), for whole-map validation."""
        probs = probs.float()
        ce = F.nll_loss(torch.log(probs.clamp_min(EPS)), target, weight=self.weights)
        dice = soft_dice(probs, target, self.dice_classes)
        return self.ce_weight * ce + self.dice_weight * dice
