"""Tests for train/model.py and train/predict.py: model shape, freezing, sliding windows."""

import numpy as np
import pytest
import torch

from train.model import (
    NUM_CLASSES,
    build_model,
    pick_device,
    preprocess,
    set_encoder_frozen,
    train_mode,
)
from train.predict import predict_mask, predict_probs, tile_starts


@pytest.fixture(scope="module")
def model() -> torch.nn.Module:
    """A U-Net with random weights (no download in tests)."""
    torch.manual_seed(0)
    return build_model(encoder_weights=None)


def test_model_outputs_one_logit_per_class(model: torch.nn.Module) -> None:
    out = model.eval()(torch.zeros(1, 3, 256, 256))
    assert out.shape == (1, NUM_CLASSES, 256, 256)


def test_preprocess_normalizes_to_chw() -> None:
    x = preprocess(np.full((4, 5, 3), 255, np.uint8))
    assert x.shape == (3, 4, 5) and x.dtype == torch.float32
    assert x[0, 0, 0] == pytest.approx((1 - 0.485) / 0.229)


def test_frozen_encoder_has_no_grad_and_eval_batchnorm(model: torch.nn.Module) -> None:
    set_encoder_frozen(model, True)
    train_mode(model, encoder_frozen=True)
    assert not any(p.requires_grad for p in model.encoder.parameters())
    assert all(p.requires_grad for p in model.decoder.parameters())
    assert not model.encoder.training and model.decoder.training
    set_encoder_frozen(model, False)
    assert all(p.requires_grad for p in model.encoder.parameters())


def test_pick_device_falls_back_to_cpu() -> None:
    if not torch.cuda.is_available():
        assert pick_device("auto").type in ("cpu", "xpu")
    assert pick_device("cpu").type == "cpu"


def test_tiles_cover_the_map_and_end_at_the_edge() -> None:
    assert tile_starts(100, 256, 192) == [0]
    assert tile_starts(800, 256, 192) == [0, 192, 384, 544]
    starts = tile_starts(1000, 256, 192)
    assert starts[-1] + 256 == 1000
    assert all(b - a <= 192 for a, b in zip(starts, starts[1:], strict=False))


def test_sliding_window_probabilities_cover_any_map_size(model: torch.nn.Module) -> None:
    image = np.random.default_rng(0).integers(0, 255, (300, 200, 3), dtype=np.uint8)
    probs = predict_probs(model, image, torch.device("cpu"), batch_size=2)
    assert probs.shape == (NUM_CLASSES, 300, 200)
    assert torch.allclose(probs.sum(0), torch.ones(300, 200), atol=1e-5)
    mask = predict_mask(model, image, torch.device("cpu"))
    assert mask.shape == (300, 200) and mask.dtype == np.uint8
