"""Tests for train/losses.py: class weights and the CE + Dice loss."""

import pytest
import torch

from train.losses import SegLoss, class_weights, split_shares


def test_class_weights_relative_to_background_and_capped() -> None:
    weights = class_weights([0.94, 0.053, 0.005, 0.0], cap=20.0)
    assert weights[0] == pytest.approx(1.0)
    assert weights[1] == pytest.approx((0.94 / 0.053) ** 0.5)
    assert weights[2] == pytest.approx((0.94 / 0.005) ** 0.5)
    assert weights[3] == 20.0  # no pixels at all -> the cap


def test_split_shares_weight_maps_by_area() -> None:
    rows = [
        {
            "width": 10,
            "height": 10,
            "share_background": 1.0,
            "share_wall": 0.0,
            "share_portal": 0.0,
            "share_light": 0.0,
        },
        {
            "width": 30,
            "height": 10,
            "share_background": 0.6,
            "share_wall": 0.4,
            "share_portal": 0.0,
            "share_light": 0.0,
        },
    ]
    assert split_shares(rows) == pytest.approx([0.7, 0.3, 0.0, 0.0])


def test_loss_is_low_for_a_right_prediction_and_high_for_a_wrong_one() -> None:
    target = torch.zeros(2, 16, 16, dtype=torch.long)
    target[:, 4:6, :] = 1
    target[:, 10, 3:7] = 2
    loss_fn = SegLoss([1.0, 4.0, 13.0, 20.0])
    right = torch.nn.functional.one_hot(target, 4).permute(0, 3, 1, 2).float() * 20
    wrong = right.roll(shifts=1, dims=1)  # every pixel predicts another class
    assert loss_fn(right, target) < 0.05
    assert loss_fn(wrong, target) > 5


def test_loss_from_probs_matches_loss_from_logits() -> None:
    torch.manual_seed(0)
    logits = torch.randn(1, 4, 8, 8)
    target = torch.randint(0, 4, (1, 8, 8))
    loss_fn = SegLoss([1.0, 2.0, 3.0, 4.0])
    assert loss_fn.from_probs(logits.softmax(1), target) == pytest.approx(
        float(loss_fn(logits, target)), rel=1e-4
    )
