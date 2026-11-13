"""Images shown to Claude: crops of the map with a labeled grid, and overlays of an answer.

Claude places walls in grid squares, so every image carries the square numbers in a margin and
thin grid lines over the map. The same function draws a submitted answer on top, which lets the
model check its own work.
"""

import base64
import io

from PIL import Image, ImageDraw, ImageFont

MARGIN = 26  # px, room for the square numbers on the top and left
WALL_RGB, PORTAL_RGB, LIGHT_RGB = (255, 40, 40), (255, 0, 255), (255, 210, 0)

Box = tuple[float, float, float, float]  # x0, y0, x1, y1 in grid squares


def clamp_box(box: Box, map_size: tuple[float, float]) -> Box:
    """Keep the window inside the map and at least one square wide and high."""
    w, h = map_size
    x0, x1 = sorted((box[0], box[2]))
    y0, y1 = sorted((box[1], box[3]))
    x0, y0 = max(0.0, min(x0, w - 1)), max(0.0, min(y0, h - 1))
    x1, y1 = min(float(w), max(x1, x0 + 1)), min(float(h), max(y1, y0 + 1))
    return x0, y0, x1, y1


def _label_step(zoom: float) -> int:
    """Number every square when zoomed in, every 2nd or 5th when squares get small."""
    return 1 if zoom >= 40 else 2 if zoom >= 20 else 5


def render_view(
    image: Image.Image,
    ppg: float,
    box: Box,
    max_px: int = 1300,
    max_zoom: float = 160,
    uvtt: dict | None = None,
) -> tuple[Image.Image, float]:
    """Crop `box` (grid squares) from the map, zoom it and add the labeled grid.

    `ppg` is the map image's pixels per square. The crop is scaled so its longest side is at
    most `max_px`, and never beyond `max_zoom` px per square. With `uvtt`, its walls (red),
    portals (magenta) and lights (yellow rings) are drawn on top. Returns the image and the
    zoom used, in px per square.
    """
    x0, y0, x1, y1 = clamp_box(box, (image.width / ppg, image.height / ppg))
    zoom = min(max_zoom, max_px / max(x1 - x0, y1 - y0))
    crop = image.convert("RGB").crop(
        (round(x0 * ppg), round(y0 * ppg), round(x1 * ppg), round(y1 * ppg))
    )
    crop = crop.resize((round((x1 - x0) * zoom), round((y1 - y0) * zoom)), Image.LANCZOS)
    canvas = Image.new("RGB", (crop.width + MARGIN, crop.height + MARGIN), "black")
    canvas.paste(crop, (MARGIN, MARGIN))
    draw = ImageDraw.Draw(canvas, "RGBA")

    def px(x: float, y: float) -> tuple[float, float]:
        return MARGIN + (x - x0) * zoom, MARGIN + (y - y0) * zoom

    _draw_grid(draw, canvas.size, (x0, y0, x1, y1), zoom)
    if uvtt is not None:
        _draw_answer(draw, uvtt, px, zoom)
    return canvas, zoom


def _draw_grid(draw: ImageDraw.ImageDraw, size: tuple[int, int], box: Box, zoom: float) -> None:
    """Grid lines on whole squares, half-square ticks and square numbers in the margin."""
    x0, y0, x1, y1 = box
    font = ImageFont.load_default(size=15)
    step = _label_step(zoom)
    for axis, (lo, hi) in enumerate(((x0, x1), (y0, y1))):
        half = int(lo * 2) if lo * 2 == int(lo * 2) else int(lo * 2) + 1
        while half / 2 <= hi:
            v = half / 2
            p = MARGIN + (v - lo) * zoom
            whole = half % 2 == 0
            tick = 10 if whole else 5
            if axis == 0:
                draw.line([(p, MARGIN - tick), (p, MARGIN)], fill="yellow", width=2)
            else:
                draw.line([(MARGIN - tick, p), (MARGIN, p)], fill="yellow", width=2)
            if whole:
                color = (0, 255, 255, 110) if axis == 0 else (255, 0, 255, 110)
                end = (p, size[1]) if axis == 0 else (size[0], p)
                draw.line([(p, MARGIN) if axis == 0 else (MARGIN, p), end], fill=color, width=1)
                if int(v) % step == 0:
                    at = (p + 3, 2) if axis == 0 else (2, p + 2)
                    draw.text(at, str(int(v)), fill="yellow", font=font)
            half += 1


def _draw_answer(draw: ImageDraw.ImageDraw, uvtt: dict, px, zoom: float) -> None:
    """Thin lines for walls and portals and rings for lights, so the map stays visible."""
    width = max(2, round(zoom * 0.06))
    for line in uvtt.get("line_of_sight", []):
        draw.line([px(p["x"], p["y"]) for p in line], fill=(*WALL_RGB, 230), width=width)
    for portal in uvtt.get("portals", []):
        a, b = portal["bounds"]
        draw.line(
            [px(a["x"], a["y"]), px(b["x"], b["y"])], fill=(*PORTAL_RGB, 240), width=width + 2
        )
    for light in uvtt.get("lights", []):
        cx, cy = px(light["position"]["x"], light["position"]["y"])
        r = 0.3 * zoom
        draw.ellipse([cx - r, cy - r, cx + r, cy + r], outline=(*LIGHT_RGB, 255), width=width)


def to_image_block(image: Image.Image, quality: int = 85) -> dict:
    """The image as a base64 JPEG content block for the Messages API."""
    buf = io.BytesIO()
    image.save(buf, format="JPEG", quality=quality)
    data = base64.standard_b64encode(buf.getvalue()).decode("ascii")
    return {"type": "image", "source": {"type": "base64", "media_type": "image/jpeg", "data": data}}
