"""Draw a dressed layout into a map image, then apply image effects.

Floors and ground are full-map textures (data/synth/textures.py), cut to each region. Walls,
doors, windows, furniture and light sources are vector drawings on transparent layers at twice
the final resolution, scaled down for smooth edges and composited in order:

    ground and floors -> rugs, furniture, floor lights -> walls -> doors, windows, wall lights

Effects come last: baked lighting (dark ambient plus glows around lit lights), grid lines,
a color tint, blur and JPEG noise, each with the probability set in the config.
"""

import io
import math

import numpy as np
from PIL import Image, ImageDraw, ImageFilter

from data.synth import textures
from data.synth.dress import Item
from data.synth.layout import Layout, Opening

SUPERSAMPLE = 2
INK = (28, 24, 20, 255)  # outline color, like the ink lines of hand-drawn maps

WALL_COLORS = [(40, 38, 36), (70, 66, 60), (105, 100, 92), (85, 60, 40), (190, 185, 170)]
DOOR_COLORS = [(120, 80, 45), (95, 60, 35), (140, 100, 60), (80, 80, 85)]
FABRIC = [(140, 40, 40), (40, 70, 130), (60, 110, 60), (150, 120, 60), (110, 60, 110)]


class Canvas:
    """A transparent RGBA layer at SUPERSAMPLE x the map resolution, drawn in grid squares."""

    def __init__(self, width_px: int, height_px: int, ppg: int):
        """An empty layer for a map of width_px x height_px at ppg pixels per square."""
        self.k = ppg * SUPERSAMPLE
        self.image = Image.new("RGBA", (width_px * SUPERSAMPLE, height_px * SUPERSAMPLE))
        self.draw = ImageDraw.Draw(self.image)

    def px(self, x: float, y: float) -> tuple[float, float]:
        """Grid point -> layer pixel."""
        return x * self.k, y * self.k

    def w(self, squares: float) -> int:
        """A line width in squares -> layer pixels (at least 1)."""
        return max(1, round(squares * self.k))

    def rect(self, cx: float, cy: float, w: float, h: float, fill, outline=INK, line=0.03) -> None:
        """A rectangle centered on (cx, cy), w x h squares."""
        box = [*self.px(cx - w / 2, cy - h / 2), *self.px(cx + w / 2, cy + h / 2)]
        self.draw.rectangle(box, fill=fill, outline=outline, width=self.w(line) if outline else 0)

    def circle(self, cx: float, cy: float, r: float, fill, outline=INK, line=0.03) -> None:
        """A circle of radius r squares centered on (cx, cy)."""
        box = [*self.px(cx - r, cy - r), *self.px(cx + r, cy + r)]
        self.draw.ellipse(box, fill=fill, outline=outline, width=self.w(line) if outline else 0)

    def line(self, points: list[tuple[float, float]], fill, width: float) -> None:
        """A polyline through grid points, `width` squares wide, with rounded joints."""
        self.draw.line([self.px(*p) for p in points], fill=fill, width=self.w(width), joint="curve")

    def downscaled(self) -> Image.Image:
        """The layer at the map resolution (alpha-correct: premultiplied while resizing)."""
        size = (self.image.width // SUPERSAMPLE, self.image.height // SUPERSAMPLE)
        return self.image.convert("RGBa").resize(size, Image.LANCZOS).convert("RGBA")


def _color(rng: np.random.Generator, palette: list, jitter: float = 15) -> tuple[int, ...]:
    """A jittered color from `palette`, as an RGBA tuple."""
    base = np.array(palette[int(rng.integers(len(palette)))], dtype=float)
    rgb = np.clip(base + rng.uniform(-jitter, jitter, size=3), 0, 255).astype(int)
    return (*map(int, rgb), 255)


def _darker(color: tuple[int, ...], f: float = 0.6) -> tuple[int, ...]:
    """The color with its RGB scaled by f."""
    return (*(int(c * f) for c in color[:3]), 255)


def flame(c: Canvas, x: float, y: float, r: float) -> None:
    """A fire: orange outside, yellow, then a pale core."""
    c.circle(x, y, r, (235, 110, 30, 255), outline=None)
    c.circle(x, y - r * 0.1, r * 0.65, (255, 195, 60, 255), outline=None)
    c.circle(x, y - r * 0.15, r * 0.32, (255, 245, 190, 255), outline=None)


def _stone_ring(c: Canvas, rng: np.random.Generator, x: float, y: float, r: float, n: int) -> None:
    """A ring of n gray stones of radius r around (x, y)."""
    for i in range(n):
        a = 2 * math.pi * i / n + float(rng.uniform(-0.1, 0.1))
        s = r * float(rng.uniform(0.18, 0.26))
        c.circle(x + r * math.cos(a), y + r * math.sin(a), s, _color(rng, [(125, 120, 110)]))


def draw_light(c: Canvas, rng: np.random.Generator, item: Item) -> None:
    """A light source or unlit fixture; lit ones get a flame."""
    x, y, kind = item.x, item.y, item.kind
    ash = (70, 68, 65, 255)
    if kind == "torch":
        nx, ny = item.normal
        c.line([(x - nx * 0.2, y - ny * 0.2), (x, y)], (60, 45, 30, 255), 0.06)
        c.circle(x, y, 0.07, (90, 65, 40, 255))
        if item.lit:
            flame(c, x, y, float(rng.uniform(0.11, 0.16)))
    elif kind == "candle":
        c.circle(x, y, 0.06, (235, 225, 200, 255))
        if item.lit:
            flame(c, x, y, 0.05)
    elif kind == "lantern":
        c.rect(x, y, 0.26, 0.26, (50, 45, 40, 255))
        c.rect(x, y, 0.15, 0.15, (255, 210, 100, 255) if item.lit else (90, 95, 100, 255))
    elif kind == "brazier":
        c.circle(x, y, 0.32, (55, 50, 48, 255), line=0.04)
        c.circle(x, y, 0.24, (120, 40, 20, 255) if item.lit else ash, outline=None)
        if item.lit:
            flame(c, x, y, 0.2)
    elif kind == "campfire":
        _stone_ring(c, rng, x, y, 0.33, 8)
        for a in (0.4, 2.0):
            dx, dy = 0.22 * math.cos(a), 0.22 * math.sin(a)
            c.line([(x - dx, y - dy), (x + dx, y + dy)], (100, 70, 40, 255), 0.08)
        if item.lit:
            flame(c, x, y, 0.2)
        else:
            c.circle(x, y, 0.12, (35, 33, 30, 255), outline=None)
    elif kind == "bonfire":
        _stone_ring(c, rng, x, y, 0.65, 12)
        for a in (0.2, 1.3, 2.4):
            dx, dy = 0.45 * math.cos(a), 0.45 * math.sin(a)
            c.line([(x - dx, y - dy), (x + dx, y + dy)], (95, 65, 35, 255), 0.13)
        if item.lit:
            flame(c, x, y, 0.45)
    elif kind == "fireplace":
        nx, ny = item.normal
        hx, hy = x - nx * 0.15, y - ny * 0.15
        w, h = (0.9, 0.55) if ny else (0.55, 0.9)
        c.rect(hx, hy, w, h, _color(rng, [(130, 120, 110)]), line=0.04)
        c.rect(hx, hy, w * 0.6 if ny else w * 0.5, h * 0.5 if ny else h * 0.6, (30, 28, 26, 255))
        if item.lit:
            flame(c, x, y, 0.17)


def draw_furniture(c: Canvas, rng: np.random.Generator, item: Item) -> None:
    """A piece of furniture or a rug, with ink outlines."""
    x, y, w, h = item.x, item.y, item.w, item.h
    wood = _color(rng, textures.WOOD)
    if item.kind == "rug":
        c.rect(x, y, w, h, _color(rng, FABRIC), outline=None)
        c.rect(x, y, w - 0.2, h - 0.2, None, outline=_color(rng, FABRIC), line=0.05)
    elif item.kind == "table":
        for dx, dy in ((0, -0.45), (0, 0.45), (-0.45, 0), (0.45, 0)):
            if rng.random() < 0.7:
                c.rect(x + dx, y + dy, 0.22, 0.22, _darker(wood, 0.8))
        if rng.random() < 0.5:
            c.circle(x, y, w / 2, wood)
        else:
            c.rect(x, y, w, h, wood)
    elif item.kind == "barrel":
        c.circle(x, y, w / 2, wood, line=0.04)
        c.circle(x, y, w / 2 - 0.08, None, outline=_darker(wood), line=0.03)
    elif item.kind == "crate":
        c.rect(x, y, w, h, wood, line=0.04)
        c.line([(x - w / 2, y - h / 2), (x + w / 2, y + h / 2)], _darker(wood), 0.04)
        c.line([(x - w / 2, y + h / 2), (x + w / 2, y - h / 2)], _darker(wood), 0.04)
    elif item.kind == "pillar":
        stone = _color(rng, textures.STONE)
        if rng.random() < 0.5:
            c.circle(x, y, w / 2, stone, line=0.04)
        else:
            c.rect(x, y, w, w, stone, line=0.04)
    elif item.kind in ("shelf", "counter"):
        c.rect(x, y, w, h, _darker(wood, 0.75) if item.kind == "shelf" else wood, line=0.04)
        if item.kind == "shelf":
            long_x = w > h
            n = int(max(w, h) / 0.12)
            for i in range(n):
                t = -max(w, h) / 2 + 0.06 + i * 0.12
                bx, by = (x + t, y) if long_x else (x, y + t)
                bw, bh = (0.08, min(w, h) * 0.6) if long_x else (min(w, h) * 0.6, 0.08)
                c.rect(bx, by, bw, bh, _color(rng, FABRIC, 30), outline=None)
    elif item.kind == "bed":
        nx, ny = item.normal
        depth, along = (h, w) if ny else (w, h)
        c.rect(x, y, w, h, _color(rng, FABRIC), line=0.04)
        pillow_x, pillow_y = x - nx * (depth / 2 - 0.17), y - ny * (depth / 2 - 0.17)
        pw, ph = (along * 0.85, 0.22) if ny else (0.22, along * 0.85)
        c.rect(pillow_x, pillow_y, pw, ph, (235, 230, 220, 255))


def draw_opening(
    c: Canvas, rng: np.random.Generator, o: Opening, wall_w: float, wall_color, door_color
) -> None:
    """A door (closed or open) or a window in the wall; gaps draw nothing."""
    if o.kind == "gap":
        return
    (ax, ay), (bx, by) = o.endpoints()
    for px_, py_ in ((ax, ay), (bx, by)):  # jamb posts in the wall's color
        c.rect(px_, py_, wall_w, wall_w, wall_color, outline=None)
    horizontal = o.orient == "h"
    mx, my = (ax + bx) / 2, (ay + by) / 2
    if o.kind == "window":
        w, h = (
            (o.length - wall_w, wall_w * 0.7) if horizontal else (wall_w * 0.7, o.length - wall_w)
        )
        c.rect(mx, my, w, h, _darker(wall_color, 1.25), line=0.02)
        glass = (170, 205, 225, 255) if rng.random() < 0.7 else INK
        gw, gh = (w, 0.05) if horizontal else (0.05, h)
        c.rect(mx, my, gw, gh, glass, outline=None)
        return
    leaves = (
        [((ax, ay), (mx, my)), ((bx, by), (mx, my))] if o.length == 2 else [((ax, ay), (bx, by))]
    )
    open_side = int(rng.choice([-1, 1])) if rng.random() < 0.25 else 0
    for (hx, hy), (ex, ey) in leaves:
        if open_side:  # swung open, perpendicular to the wall
            length = math.hypot(ex - hx, ey - hy)
            ex, ey = (hx, hy + open_side * length) if horizontal else (hx + open_side * length, hy)
        c.line([(hx, hy), (ex, ey)], INK, 0.2)
        c.line([(hx, hy), (ex, ey)], door_color, 0.14)


def _composite(base: np.ndarray, layer: Image.Image) -> np.ndarray:
    """Alpha-composite an RGBA layer over a float RGB array."""
    rgba = np.asarray(layer, dtype=np.float32)
    alpha = rgba[..., 3:4] / 255.0
    return base * (1 - alpha) + rgba[..., :3] * alpha


def _glow(rng: np.random.Generator, img: np.ndarray, items: list[Item], ppg: int) -> np.ndarray:
    """Baked lighting: dark ambient, warm glows around lit lights (glow size is random)."""
    height, width = img.shape[:2]
    light = np.full((height, width), rng.uniform(0.35, 0.75), dtype=np.float32)
    warm = np.zeros((height, width), dtype=np.float32)
    for item in (i for i in items if i.lit):
        radius = rng.uniform(1.5, 4.5) * ppg
        cx, cy = item.x * ppg, item.y * ppg
        x0, x1 = int(max(0, cx - radius)), int(min(width, cx + radius))
        y0, y1 = int(max(0, cy - radius)), int(min(height, cy + radius))
        if x1 <= x0 or y1 <= y0:
            continue
        ys, xs = np.mgrid[y0:y1, x0:x1]
        d = np.hypot(xs - cx, ys - cy) / radius
        warm[y0:y1, x0:x1] += np.clip(1 - d, 0, 1) ** 2 * rng.uniform(0.5, 0.9)
    tint = np.array([1.0, 0.85, 0.6], dtype=np.float32)
    return img * (light[..., None] + warm[..., None] * tint)


def _grid(rng: np.random.Generator, img: np.ndarray, ppg: int) -> np.ndarray:
    """Grid lines every square, dark or light, 1-2 px, partly transparent."""
    color = np.array((0, 0, 0) if rng.random() < 0.8 else (255, 255, 255), dtype=np.float32)
    alpha = rng.uniform(0.12, 0.4)
    thick = int(rng.integers(1, 3))
    mask = np.zeros(img.shape[:2], dtype=bool)
    for t in range(thick):
        mask[t::ppg, :] = True
        mask[:, t::ppg] = True
    img[mask] = img[mask] * (1 - alpha) + color * alpha
    return img


def render(
    rng: np.random.Generator, layout: Layout, items: list[Item], cfg: dict, ppg: int
) -> tuple[Image.Image, dict]:
    """Draw the map; return the RGB image and which effects were applied."""
    height_px, width_px = layout.height * ppg, layout.width * ppg
    shape = (height_px, width_px)
    regions_px = np.kron(layout.regions, np.ones((ppg, ppg), dtype=np.int32))

    img = textures.ground_texture(rng, shape, ppg)
    floors = [textures.floor_texture(rng, shape, ppg) for _ in range(int(rng.integers(1, 4)))]
    for rid in sorted(layout.kinds):
        floor = floors[int(rng.integers(len(floors)))]
        sel = regions_px == rid
        img[sel] = floor[sel]

    under = Canvas(width_px, height_px, ppg)
    for item in items:
        if item.kind == "rug":
            draw_furniture(under, rng, item)
    for item in items:
        if item.tier is None and item.kind != "rug":
            draw_furniture(under, rng, item)
        elif item.tier is not None and item.normal is None:
            draw_light(under, rng, item)
    img = _composite(img, under.downscaled())

    wcfg = cfg["walls"]
    wall_w = float(rng.uniform(*wcfg["width"]))
    wall_color = _color(rng, WALL_COLORS)
    walls = Canvas(width_px, height_px, ppg)
    outline = rng.random() < wcfg["outline_probability"]
    for poly in layout.walls:
        if outline:
            walls.line(poly, INK, wall_w + 0.08)
    for poly in layout.walls:
        walls.line(poly, wall_color, wall_w)
    layer = np.asarray(walls.downscaled(), dtype=np.float32).copy()
    layer[..., :3] *= (0.8 + 0.4 * textures.value_noise(rng, shape, ppg / 3))[..., None]
    img = _composite(img, Image.fromarray(np.clip(layer, 0, 255).astype(np.uint8)))

    over = Canvas(width_px, height_px, ppg)
    door_color = _color(rng, DOOR_COLORS)
    for opening in layout.openings:
        draw_opening(over, rng, opening, wall_w, wall_color, door_color)
    for item in items:
        if item.tier is not None and item.normal is not None:
            draw_light(over, rng, item)
    img = _composite(img, over.downscaled())

    ecfg = cfg["effects"]
    applied = {
        name: bool(rng.random() < ecfg[f"{name}_probability"])
        for name in ("glow", "grid", "tint", "blur", "jpeg")
    }
    if applied["glow"]:
        img = _glow(rng, img, items, ppg)
    if applied["grid"]:
        img = _grid(rng, img, ppg)
    if applied["tint"]:
        img = img * rng.uniform(0.85, 1.15, size=3).astype(np.float32)
    image = Image.fromarray(np.clip(img, 0, 255).astype(np.uint8))
    if applied["blur"]:
        image = image.filter(ImageFilter.GaussianBlur(float(rng.uniform(0.5, 1.2))))
    if applied["jpeg"]:
        buf = io.BytesIO()
        image.save(buf, format="JPEG", quality=int(rng.integers(40, 86)))
        image = Image.open(io.BytesIO(buf.getvalue())).convert("RGB")
    return image, applied
