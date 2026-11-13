"""The preview the user sees: the map with the suggested walls, portals and lights over it.

Drawn from the stored image fractions, so a map-size change never moves anything. The colors
are the ones the model sees its own answer in (`llm/views.py`), so the legend matches both.
"""

from PIL import Image, ImageDraw

from app.domain import TraceResult, to_pixels
from llm.views import LIGHT_RGB, PORTAL_RGB, WALL_RGB

LEGEND = "Walls: red · Doors and windows: magenta · Lights: yellow rings"
LIGHT_RING_SQUARES = 0.3  # ring radius in grid squares of the traced map


def line_width(image: Image.Image) -> int:
    """Line width in px, scaled to the image's longer side (3 px on a 1750 px map)."""
    return max(2, round(max(image.size) / 600))


def overlay(image: Image.Image, result: TraceResult | None) -> Image.Image:
    """A copy of `image` with the result drawn over it; the input is never changed."""
    out = image.convert("RGB").copy()
    if result is None:
        return out
    draw = ImageDraw.Draw(out)
    width = line_width(out)
    size = out.size

    def px(point) -> tuple[float, float]:
        """A point in pixels on this image."""
        return to_pixels(point, size)

    for wall in result.walls:
        draw.line([px(p) for p in wall.points], fill=WALL_RGB, width=width, joint="curve")
    for portal in result.portals:
        draw.line([px(portal.a), px(portal.b)], fill=PORTAL_RGB, width=width + 2)
    radius = LIGHT_RING_SQUARES * out.width / result.traced_size.width
    for light in result.lights:
        cx, cy = px(light.at)
        box = [cx - radius, cy - radius, cx + radius, cy + radius]
        draw.ellipse(box, outline=LIGHT_RGB, width=width)
    return out
