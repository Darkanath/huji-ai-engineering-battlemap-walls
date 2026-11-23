"""The preview the user sees: the map with the suggested walls, portals and lights over it.

Drawn from the stored image fractions, so a map-size change never moves anything. The colors
are the ones the model sees its own answer in (`llm/views.py`), so the legend matches both.
"""

from PIL import Image, ImageDraw, ImageFont

from app.domain import TraceResult, to_pixels
from app.progress import BoardSnapshot
from llm.orchestrator import ChunkState
from llm.review import ReviewState
from llm.views import LIGHT_RGB, PORTAL_RGB, STRIP_RGBA, WALL_RGB

LEGEND = "Walls: red · Doors and windows: magenta · Lights: yellow rings"
LIGHT_RING_SQUARES = 0.3  # ring radius in grid squares of the traced map
# The chunked pass's board (contracts/app.md): each part's tint by state.
STATE_RGB = {
    ChunkState.waiting: (170, 170, 170),
    ChunkState.tracing: (40, 120, 255),
    ChunkState.done: (40, 200, 80),
    ChunkState.failed: (230, 40, 40),
    ChunkState.skipped: (120, 120, 120),
}
FILL_ALPHA = 90  # how strongly a part is tinted (0-255)
UNTRACED_RGB = (200, 200, 200)
DASH = 12  # px, the untraced outline's dash length


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
    for a, b in result.untraced:
        _dashed_rectangle(draw, px(a), px(b), UNTRACED_RGB, width)
    return out


def _dashed_rectangle(draw: ImageDraw.ImageDraw, a, b, color, width: int) -> None:
    """A rectangle from corner `a` to corner `b` (pixels) drawn as dashes."""
    (x0, y0), (x1, y1) = a, b
    for (sx, sy), (ex, ey) in (
        ((x0, y0), (x1, y0)),
        ((x1, y0), (x1, y1)),
        ((x1, y1), (x0, y1)),
        ((x0, y1), (x0, y0)),
    ):
        length = max(abs(ex - sx), abs(ey - sy))
        steps = max(1, int(length // DASH))
        for i in range(0, steps, 2):
            t0, t1 = i / steps, min(1.0, (i + 1) / steps)
            draw.line(
                [
                    (sx + (ex - sx) * t0, sy + (ey - sy) * t0),
                    (sx + (ex - sx) * t1, sy + (ey - sy) * t1),
                ],
                fill=color,
                width=width,
            )


def chunk_overlay(
    image: Image.Image, snapshot: BoardSnapshot, map_size: tuple[int, int]
) -> Image.Image:
    """The map with the chunked pass's board on it: each part tinted by its state, outlined
    and numbered (a skipped part also crossed out), and the seam strips in amber while the
    orchestrator reviews them. The input image is never changed."""
    out = image.convert("RGB").copy()
    draw = ImageDraw.Draw(out, "RGBA")
    scale = out.width / map_size[0]  # px per square, on both axes as in the model's views
    width = line_width(out)
    font = ImageFont.load_default(size=max(14, round(scale * 1.2)))

    def box(b) -> list[float]:
        """A box in squares as pixel corners."""
        return [b[0] * scale, b[1] * scale, b[2] * scale, b[3] * scale]

    if snapshot.review == ReviewState.reviewing:
        for seam in snapshot.seams:
            draw.rectangle(box(seam.strip), fill=STRIP_RGBA)
    for chunk, state in zip(snapshot.layout, snapshot.states, strict=True):
        color = STATE_RGB[state]
        corners = box(chunk.core)
        draw.rectangle(corners, fill=(*color, FILL_ALPHA), outline=color, width=width)
        if state == ChunkState.skipped:
            draw.line(corners, fill=color, width=width)
            draw.line([corners[0], corners[3], corners[2], corners[1]], fill=color, width=width)
        at = (corners[0] + 3 * width, corners[1] + 2 * width)
        draw.text(
            at, str(chunk.index + 1), fill="white", font=font, stroke_width=2, stroke_fill="black"
        )
    return out
