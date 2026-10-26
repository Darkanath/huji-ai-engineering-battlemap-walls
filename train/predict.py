"""Whole-map inference with sliding windows (docs/training.md §6).

The map (at 32 px per square) is covered with `window`×`window` tiles every `stride` px; the
last row and column of tiles are moved in so they end at the map's edge. Softmax probabilities
are averaged where tiles overlap, and the class is the argmax. Maps smaller than a tile are
padded with black and the padding is cut off again.

Validation during training and the app use this same code, so a validation score is what the
app would produce.
"""

from pathlib import Path

import numpy as np
import torch
from torch import nn

from train.model import NUM_CLASSES, build_model, preprocess


def tile_starts(length: int, window: int, stride: int) -> list[int]:
    """Start offsets of tiles covering `length` px; the last tile ends exactly at the edge."""
    if length <= window:
        return [0]
    starts = list(range(0, length - window, stride))
    return starts + [length - window]


@torch.no_grad()
def predict_probs(
    model: nn.Module,
    image: np.ndarray,
    device: torch.device,
    window: int = 256,
    stride: int = 192,
    batch_size: int = 8,
    channels_last: bool = False,
) -> torch.Tensor:
    """Class probabilities (C, H, W) on the CPU for a uint8 RGB image (H, W, 3)."""
    model.eval()
    height, width = image.shape[:2]
    pad_h, pad_w = max(0, window - height), max(0, window - width)
    if pad_h or pad_w:
        image = np.pad(image, ((0, pad_h), (0, pad_w), (0, 0)))
    x = preprocess(image)
    full_h, full_w = x.shape[1:]

    probs = torch.zeros(NUM_CLASSES, full_h, full_w)
    counts = torch.zeros(1, full_h, full_w)
    tiles = [
        (top, left)
        for top in tile_starts(full_h, window, stride)
        for left in tile_starts(full_w, window, stride)
    ]
    memory_format = torch.channels_last if channels_last else torch.contiguous_format
    for i in range(0, len(tiles), batch_size):
        batch_tiles = tiles[i : i + batch_size]
        batch = torch.stack([x[:, t : t + window, s : s + window] for t, s in batch_tiles])
        batch = batch.to(device, memory_format=memory_format)
        out = model(batch).float().softmax(dim=1).cpu()
        for (top, left), p in zip(batch_tiles, out, strict=True):
            probs[:, top : top + window, left : left + window] += p
            counts[:, top : top + window, left : left + window] += 1
    return (probs / counts)[:, :height, :width]


def predict_mask(model: nn.Module, image: np.ndarray, device: torch.device, **kwargs) -> np.ndarray:
    """Class-id mask (H, W) uint8 for a uint8 RGB image; kwargs go to `predict_probs`."""
    return predict_probs(model, image, device, **kwargs).argmax(dim=0).numpy().astype(np.uint8)


def load_checkpoint_model(path: Path, device: torch.device) -> tuple[nn.Module, dict]:
    """The model saved in a checkpoint (best.pt or last.pt) and the run config it was saved with.

    The encoder is built without pretrained weights: the checkpoint holds all of them.
    """
    checkpoint = torch.load(path, map_location="cpu", weights_only=False)
    cfg = checkpoint["config"]
    model = build_model(cfg["model"]["arch"], cfg["model"]["encoder"], encoder_weights=None)
    model.load_state_dict(checkpoint["model"])
    return model.to(device).eval(), cfg
