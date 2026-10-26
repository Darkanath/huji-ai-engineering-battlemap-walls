"""Training augmentation (docs/training.md §3), with `albumentations`.

Geometric transforms move the image and the mask together, and the mask always uses
nearest-neighbor interpolation so class ids stay exact. Color transforms change the image only.
Only training crops are augmented; validation runs on whole, unchanged maps.

- Scale jitter stays at ±10%: scale normalization (32 px per square) keeps walls about 8 px
  thick, and the jitter only covers small errors in grid detection or a user-entered map width.
- No elastic or perspective transforms: they bend straight walls, and maps are always top-down.

Every crop is augmented with its own seed (from the run seed, the epoch and the crop index), so
an epoch is the same whatever the number of DataLoader workers and after a resume.
"""

import albumentations as A
import cv2
import numpy as np


def build_augment() -> A.Compose:
    """The augmentation pipeline from the table in docs/training.md §3."""
    return A.Compose(
        [
            A.HorizontalFlip(p=0.5),
            A.VerticalFlip(p=0.5),
            # RandomRotate90 picks k in {0, 1, 2, 3}; at p=2/3 a real rotation (k in {1, 2, 3})
            # happens with probability 0.5, as in the table.
            A.RandomRotate90(p=2 / 3),
            # Scale jitter: zoom in or out by up to 10%, the output keeps its size (256).
            A.Affine(
                scale=(0.9, 1.1),
                interpolation=cv2.INTER_LINEAR,
                mask_interpolation=cv2.INTER_NEAREST,
                border_mode=cv2.BORDER_CONSTANT,
                fill=0,
                fill_mask=0,
                p=0.3,
            ),
            A.RandomBrightnessContrast(brightness_limit=0.2, contrast_limit=0.2, p=0.5),
            A.HueSaturationValue(hue_shift_limit=10, sat_shift_limit=20, val_shift_limit=10, p=0.5),
            A.RandomGamma(gamma_limit=(80, 120), p=0.2),
            A.ToGray(p=0.05),
            A.GaussianBlur(blur_limit=(3, 5), p=0.2),
            A.GaussNoise(std_range=(0.01, 0.05), p=0.2),
            A.ImageCompression(quality_range=(50, 95), p=0.3),
        ]
    )


def augment_crop(
    augment: A.Compose, image: np.ndarray, mask: np.ndarray, seed: int
) -> tuple[np.ndarray, np.ndarray]:
    """Apply `augment` to one crop with its own `seed`; returns (image, mask)."""
    augment.set_random_seed(seed)
    out = augment(image=image, mask=mask)
    return out["image"], out["mask"]
