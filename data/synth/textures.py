"""Procedural textures for floors and ground, as float32 RGB arrays (0-255) of a full map.

Each texture is made from value noise (random grids upsampled smoothly) plus a pattern: wooden
planks, square tiles, a checkerboard, plain stone, or outdoor ground. Patterns with strong
straight lines (planks, tiles, checkers) are on purpose: they look like thin walls and teach
the model that a line on the floor is not a wall.
"""

import numpy as np
from PIL import Image

RGB = tuple[float, float, float]

WOOD = [(120, 82, 50), (150, 105, 65), (95, 65, 40), (170, 130, 85), (110, 90, 70)]
STONE = [(110, 110, 105), (140, 135, 125), (85, 88, 92), (160, 150, 130), (100, 95, 85)]
TILE = [(180, 170, 150), (120, 60, 50), (70, 90, 110), (200, 195, 185), (60, 60, 65)]
GRASS = [(70, 110, 50), (90, 125, 60), (60, 95, 45)]
DIRT = [(140, 115, 80), (120, 95, 65), (165, 140, 100)]
VOID = [(25, 25, 28), (40, 38, 36), (15, 15, 18)]

FLOOR_STYLES = ["planks", "tiles", "checker", "stone"]
GROUND_STYLES = ["grass", "dirt", "void", "stone"]


def value_noise(rng: np.random.Generator, shape: tuple[int, int], cell: float) -> np.ndarray:
    """Smooth noise in [0, 1]: three octaves of random grids upsampled bicubically.

    `cell` is the size in pixels of the coarsest feature.
    """
    height, width = shape
    out = np.zeros(shape, dtype=np.float32)
    total = 0.0
    for octave in range(3):
        size = max(cell / 2**octave, 2.0)
        gh, gw = int(height / size) + 2, int(width / size) + 2
        grid = rng.random((gh, gw), dtype=np.float32)
        up = Image.fromarray(grid).resize((width, height), Image.BICUBIC)
        weight = 0.5**octave
        out += np.asarray(up, dtype=np.float32) * weight
        total += weight
    out /= total
    return np.clip((out - out.min()) / max(float(np.ptp(out)), 1e-6), 0, 1)


def _jitter(rng: np.random.Generator, color: RGB, amount: float = 18) -> np.ndarray:
    """`color` with a random shift of up to `amount` per channel."""
    return np.clip(np.array(color) + rng.uniform(-amount, amount, size=3), 0, 255)


def _pick(rng: np.random.Generator, palette: list[RGB]) -> np.ndarray:
    """A jittered color from `palette`."""
    return _jitter(rng, palette[int(rng.integers(len(palette)))])


def _shade(base: np.ndarray, factor: np.ndarray) -> np.ndarray:
    """Multiply a base color by a per-pixel brightness factor: (H, W) -> (H, W, 3)."""
    return base[None, None, :] * factor[..., None]


def planks(rng: np.random.Generator, shape: tuple[int, int], ppg: int) -> np.ndarray:
    """Wooden planks 0.2-0.5 squares wide, with per-plank tone, seams and staggered ends."""
    height, width = shape
    base = _pick(rng, WOOD)
    plank = max(3, int(ppg * rng.uniform(0.2, 0.5)))
    length = int(ppg * rng.uniform(1.0, 3.0))
    vertical = rng.random() < 0.5
    across, along = np.mgrid[0:height, 0:width] if not vertical else np.mgrid[0:width, 0:height]
    if vertical:
        across, along = across.T, along.T
    index = across // plank
    tones = rng.uniform(0.75, 1.15, size=int(index.max()) + 2).astype(np.float32)
    offsets = rng.integers(0, length, size=int(index.max()) + 2)
    factor = tones[index] * (0.85 + 0.3 * value_noise(rng, shape, ppg / 4))
    seam = (across % plank < 2) | ((along + offsets[index]) % length < 2)
    factor = np.where(seam, factor * 0.55, factor)
    return _shade(base, factor)


def tiles(rng: np.random.Generator, shape: tuple[int, int], ppg: int, checker: bool) -> np.ndarray:
    """Square tiles of 0.5 or 1 square with dark seams; a checkerboard alternates two colors."""
    height, width = shape
    size = int(ppg * (0.5 if rng.random() < 0.5 else 1.0))
    shift = int(rng.integers(0, size)) if rng.random() < 0.3 else 0
    ys, xs = np.mgrid[0:height, 0:width]
    tx, ty = (xs + shift) // size, (ys + shift) // size
    a = _pick(rng, TILE if checker else STONE)
    b = _pick(rng, TILE) if checker else a
    color = np.where(((tx + ty) % 2 == 0)[..., None], a[None, None, :], b[None, None, :])
    tones = rng.uniform(0.85, 1.12, size=(int(ty.max()) + 1, int(tx.max()) + 1))
    factor = tones[ty, tx].astype(np.float32) * (0.85 + 0.3 * value_noise(rng, shape, ppg / 3))
    seam_w = int(rng.integers(1, 4))
    seam = ((xs + shift) % size < seam_w) | ((ys + shift) % size < seam_w)
    factor = np.where(seam, factor * 0.5, factor)
    return color * factor[..., None]


def plain(rng: np.random.Generator, shape: tuple[int, int], ppg: int, palette: list) -> np.ndarray:
    """A plain surface in a color from `palette`, with large and small noise."""
    base = _pick(rng, palette)
    coarse = value_noise(rng, shape, ppg * 2.0)
    fine = value_noise(rng, shape, ppg / 6)
    return _shade(base, 0.7 + 0.35 * coarse + 0.15 * (fine - 0.5))


def floor_texture(rng: np.random.Generator, shape: tuple[int, int], ppg: int) -> np.ndarray:
    """A random floor texture for the whole map (planks, tiles, checker or stone)."""
    style = FLOOR_STYLES[int(rng.integers(len(FLOOR_STYLES)))]
    if style == "planks":
        return planks(rng, shape, ppg)
    if style in ("tiles", "checker"):
        return tiles(rng, shape, ppg, checker=style == "checker")
    return plain(rng, shape, ppg, STONE)


def ground_texture(rng: np.random.Generator, shape: tuple[int, int], ppg: int) -> np.ndarray:
    """A random texture for everything outside the rooms: grass, dirt, dark void or stone."""
    style = GROUND_STYLES[int(rng.integers(len(GROUND_STYLES)))]
    palette = {"grass": GRASS, "dirt": DIRT, "void": VOID, "stone": STONE}[style]
    return plain(rng, shape, ppg, palette)
