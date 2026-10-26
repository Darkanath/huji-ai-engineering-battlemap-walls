"""Training crops from the 32 px per square training copies (docs/training.md §2).

Maps are read from the manifest (`image_32`, `mask_32`) and kept in memory. Each epoch draws a
fixed number of 256×256 crops (2,000 by default):

- **Every map gets the same number of crops**, whatever its size.
- **Biased crops:** by default 45% are centered on a random wall pixel, 20% on a portal pixel,
  10% on a light pixel and 25% anywhere, so rare classes show up in most batches. A map without
  pixels of the chosen class gives that crop to "anywhere".
- The sampling is seeded with `seed + epoch`, and each crop is augmented with its own seed
  (train/augment.py), so an epoch can be repeated exactly.

`python -m train.dataset --config CONFIG` prints the class shares of one epoch's crops and saves
a contact sheet of augmented crops with their masks overlaid, to check by eye before a long run.
"""

import argparse
import tomllib
from dataclasses import dataclass, field
from pathlib import Path

import numpy as np
import torch
from PIL import Image
from torch.utils.data import Dataset

from data.contact_sheet import grid
from data.manifest import read_manifest
from data.rasterize import CLASS_NAMES, overlay
from train.augment import augment_crop, build_augment
from train.model import preprocess

CLASS_IDS = {name: cls for cls, name in CLASS_NAMES.items()}
RANDOM = "random"


@dataclass
class MapData:
    """One map at 32 px per square, padded to at least one crop in each direction."""

    dataset: str
    name: str
    image: np.ndarray  # (H, W, 3) uint8
    mask: np.ndarray  # (H, W) uint8 class ids
    # Flat pixel indices of each non-background class, for centering biased crops.
    pixels: dict[int, np.ndarray] = field(default_factory=dict)


@dataclass(frozen=True)
class Crop:
    """A crop window: which map and the top-left corner in px."""

    map_index: int
    top: int
    left: int


def select_rows(rows: list[dict], split: str, datasets: list[str]) -> list[dict]:
    """Manifest rows of `split` from the given datasets."""
    return [r for r in rows if r["split"] == split and r["dataset"] in datasets]


def load_map(processed: Path, row: dict, min_size: int = 0) -> MapData:
    """Load one map's 32 px image and mask; pad with black/background up to `min_size`."""
    image = np.array(Image.open(processed / row["image_32"]).convert("RGB"))
    mask = np.array(Image.open(processed / row["mask_32"]))
    if image.shape[:2] != mask.shape:
        raise ValueError(f"{row['map']}: image {image.shape[:2]} and mask {mask.shape} differ")
    pad_h, pad_w = max(0, min_size - mask.shape[0]), max(0, min_size - mask.shape[1])
    if pad_h or pad_w:
        image = np.pad(image, ((0, pad_h), (0, pad_w), (0, 0)))
        mask = np.pad(mask, ((0, pad_h), (0, pad_w)))
    flat = mask.ravel()
    pixels = {
        cls: np.flatnonzero(flat == cls).astype(np.int32)
        for cls in CLASS_NAMES
        if cls != CLASS_IDS["background"]
    }
    return MapData(row["dataset"], row["map"], image, mask, pixels)


def load_maps(processed: Path, rows: list[dict], min_size: int = 0) -> list[MapData]:
    """`load_map` for every row."""
    return [load_map(processed, row, min_size) for row in rows]


def sample_crops(
    maps: list[MapData], count: int, size: int, bias: dict[str, float], seed: int
) -> list[Crop]:
    """`count` crops of `size` px, the same number from every map, biased by `bias`.

    `bias` maps "wall", "portal", "light" and "random" to fractions (summing to 1). The crops
    come back in a shuffled order, so batches mix maps.
    """
    rng = np.random.default_rng(seed)
    kinds = list(bias)
    probs = np.array([bias[k] for k in kinds], dtype=float)
    probs /= probs.sum()
    per_map = np.full(len(maps), count // len(maps))
    per_map[rng.permutation(len(maps))[: count % len(maps)]] += 1

    crops = []
    for index, (data, n) in enumerate(zip(maps, per_map, strict=True)):
        height, width = data.mask.shape
        for kind in rng.choice(kinds, size=n, p=probs):
            pixels = data.pixels.get(CLASS_IDS.get(kind, -1), np.empty(0))
            if len(pixels):
                cy, cx = divmod(int(rng.choice(pixels)), width)
                top, left = cy - size // 2, cx - size // 2
            else:
                top, left = rng.integers(0, height - size + 1), rng.integers(0, width - size + 1)
            top = int(np.clip(top, 0, height - size))
            left = int(np.clip(left, 0, width - size))
            crops.append(Crop(index, top, left))
    order = rng.permutation(len(crops))
    return [crops[i] for i in order]


def crop_seed(seed: int, epoch: int, index: int) -> int:
    """The augmentation seed of crop `index` in `epoch` (fits in 32 bits)."""
    return (seed * 1_000_003 + epoch * 100_003 + index) % 2**32


class CropDataset(Dataset):
    """Random training crops over a list of maps; call `set_epoch` before each epoch."""

    def __init__(
        self,
        maps: list[MapData],
        crops_per_epoch: int = 2000,
        crop_size: int = 256,
        bias: dict[str, float] | None = None,
        seed: int = 42,
        augment: bool = True,
    ):
        if not maps:
            raise ValueError("no maps to crop from")
        self.maps = maps
        self.crops_per_epoch = crops_per_epoch
        self.crop_size = crop_size
        self.bias = bias or {"wall": 0.45, "portal": 0.2, "light": 0.1, RANDOM: 0.25}
        self.seed = seed
        self.augment = build_augment() if augment else None
        self.epoch = 0
        self.crops: list[Crop] = []
        self.set_epoch(0)

    def set_epoch(self, epoch: int) -> None:
        """Draw this epoch's crops, seeded with `seed + epoch`."""
        self.epoch = epoch
        self.crops = sample_crops(
            self.maps, self.crops_per_epoch, self.crop_size, self.bias, self.seed + epoch
        )

    def __len__(self) -> int:
        return len(self.crops)

    def raw_crop(self, index: int) -> tuple[np.ndarray, np.ndarray]:
        """Crop `index` before augmentation: (image, mask)."""
        crop = self.crops[index]
        data = self.maps[crop.map_index]
        rows = slice(crop.top, crop.top + self.crop_size)
        cols = slice(crop.left, crop.left + self.crop_size)
        return data.image[rows, cols], data.mask[rows, cols]

    def crop_arrays(self, index: int) -> tuple[np.ndarray, np.ndarray]:
        """Crop `index` after augmentation, as uint8 arrays: (image, mask)."""
        image, mask = self.raw_crop(index)
        if self.augment is not None:
            seed = crop_seed(self.seed, self.epoch, index)
            image, mask = augment_crop(self.augment, image, mask, seed)
        return image, mask

    def __getitem__(self, index: int) -> tuple[torch.Tensor, torch.Tensor]:
        image, mask = self.crop_arrays(index)
        return preprocess(image), torch.from_numpy(np.ascontiguousarray(mask)).long()

    def crop_shares(self) -> dict[str, float]:
        """Pixel share of each class over this epoch's crops (before augmentation)."""
        counts = np.zeros(len(CLASS_NAMES))
        for i in range(len(self.crops)):
            counts += np.bincount(self.raw_crop(i)[1].ravel(), minlength=len(CLASS_NAMES))
        total = counts.sum()
        return {name: float(counts[cls] / total) for cls, name in CLASS_NAMES.items()}


def crop_sheet(dataset: CropDataset, count: int = 32, cols: int = 8) -> Image.Image:
    """A contact sheet of the first `count` augmented crops, masks overlaid."""
    tiles = []
    for i in range(min(count, len(dataset))):
        image, mask = dataset.crop_arrays(i)
        tiles.append(overlay(Image.fromarray(image), mask))
    labels = [dataset.maps[dataset.crops[i].map_index].name for i in range(len(tiles))]
    return grid(tiles, cols, labels)


def main(argv: list[str] | None = None) -> None:
    """Command-line entry point: crop shares of one epoch and an augmented-crop sheet."""
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--config", type=Path, required=True, help="a run config (train/configs/)")
    ap.add_argument("--processed", type=Path, help="default: the manifest's folder")
    ap.add_argument("--epoch", type=int, default=0)
    ap.add_argument("--count", type=int, default=32, help="crops on the sheet")
    ap.add_argument("--out", type=Path, default=Path("runs/sheets/augmented_crops.jpg"))
    args = ap.parse_args(argv)

    with open(args.config, "rb") as f:
        cfg = tomllib.load(f)
    data_cfg = cfg["data"]
    processed = args.processed or Path(data_cfg["manifest"]).parent
    rows = select_rows(read_manifest(processed / "manifest.csv"), "train", data_cfg["train"])
    maps = load_maps(processed, rows, data_cfg["crop_size"])
    dataset = CropDataset(
        maps, data_cfg["crops_per_epoch"], data_cfg["crop_size"], data_cfg["crop_bias"], cfg["seed"]
    )
    dataset.set_epoch(args.epoch)
    shares = ", ".join(f"{k} {v:.1%}" for k, v in dataset.crop_shares().items())
    print(f"{len(maps)} maps, {len(dataset)} crops; class shares in crops: {shares}")
    args.out.parent.mkdir(parents=True, exist_ok=True)
    crop_sheet(dataset, args.count).save(args.out, quality=90)
    print(f"-> {args.out}")


if __name__ == "__main__":
    main()
