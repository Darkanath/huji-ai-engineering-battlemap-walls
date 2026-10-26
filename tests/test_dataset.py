"""Tests for train/dataset.py and train/augment.py: crops, crop bias, augmentation."""

from collections import Counter
from pathlib import Path

import numpy as np
import pytest
import torch

from data.manifest import read_manifest
from data.rasterize import CLASS_NAMES, WALL
from train.augment import augment_crop, build_augment
from train.dataset import CropDataset, load_map, load_maps, sample_crops, select_rows


@pytest.fixture(scope="module")
def train_maps(demo_processed: Path) -> list:
    """The training maps of the demo dataset, padded to one crop."""
    rows = select_rows(read_manifest(demo_processed / "manifest.csv"), "train", ["synthetic"])
    return load_maps(demo_processed, rows, 256)


def test_crops_are_256_with_valid_classes(train_maps: list) -> None:
    dataset = CropDataset(train_maps, crops_per_epoch=16, seed=1)
    for i in range(len(dataset)):
        image, mask = dataset[i]
        assert image.shape == (3, 256, 256) and image.dtype == torch.float32
        assert mask.shape == (256, 256) and mask.dtype == torch.int64
        assert set(mask.unique().tolist()) <= set(CLASS_NAMES)


def test_epoch_is_reproducible_and_epochs_differ(train_maps: list) -> None:
    a = CropDataset(train_maps, crops_per_epoch=8, seed=3)
    b = CropDataset(train_maps, crops_per_epoch=8, seed=3)
    a.set_epoch(2)
    b.set_epoch(2)
    assert a.crops == b.crops
    assert torch.equal(a[5][0], b[5][0]) and torch.equal(a[5][1], b[5][1])
    b.set_epoch(3)
    assert a.crops != b.crops


def test_wall_bias_centers_crops_on_walls(train_maps: list) -> None:
    dataset = CropDataset(train_maps, crops_per_epoch=50, bias={"wall": 1.0}, seed=0)
    height, width = train_maps[0].mask.shape
    inside = 0
    for i, crop in enumerate(dataset.crops):
        mask = dataset.raw_crop(i)[1]
        assert (mask == WALL).any()
        # Crops near the map edge are shifted inward; all others are centered on a wall.
        if 0 < crop.top < height - 256 and 0 < crop.left < width - 256:
            assert mask[128, 128] == WALL
            inside += 1
    assert inside > 10


def test_every_map_gets_the_same_number_of_crops(train_maps: list) -> None:
    maps = train_maps * 3
    crops = sample_crops(maps, 31, 256, {"random": 1.0}, seed=0)
    counts = Counter(c.map_index for c in crops)
    assert len(crops) == 31 and max(counts.values()) - min(counts.values()) <= 1


def test_small_map_is_padded_to_one_crop(demo_processed: Path) -> None:
    row = read_manifest(demo_processed / "manifest.csv")[0]
    data = load_map(demo_processed, row, min_size=1000)
    assert data.image.shape[:2] == data.mask.shape == (1000, 1000)
    assert data.mask[900:, 900:].max() == 0  # padding is background


def test_crop_shares_sum_to_one(train_maps: list) -> None:
    shares = CropDataset(train_maps, crops_per_epoch=20, seed=0).crop_shares()
    assert sum(shares.values()) == pytest.approx(1.0)
    assert shares["wall"] > 0.07  # biased crops hold more wall than the map (7.4%)


def test_augmentation_keeps_mask_on_the_image() -> None:
    """A bright wall line on a dark crop: after any augmentation the mask's wall pixels are
    still the bright ones (geometry moves both; color changes keep bright brighter)."""
    image = np.full((256, 256, 3), 40, np.uint8)
    mask = np.zeros((256, 256), np.uint8)
    image[100:108, 30:220] = 230
    mask[100:108, 30:220] = WALL
    augment = build_augment()
    for seed in range(30):
        out_image, out_mask = augment_crop(augment, image, mask, seed)
        assert out_image.shape == (256, 256, 3) and out_mask.shape == (256, 256)
        assert set(np.unique(out_mask)) <= {0, WALL}
        gray = out_image.mean(axis=2)
        assert gray[out_mask == WALL].mean() > gray[out_mask == 0].mean() + 60
