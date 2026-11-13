"""The user's preview: the result drawn over a copy of the map."""

from PIL import Image

from app.domain import Light, MapSize, Point, Portal, TraceResult, Usage, Wall
from app.render import overlay


def plain() -> Image.Image:
    """A plain grey 400 x 400 image."""
    return Image.new("RGB", (400, 400), (90, 90, 90))


def result() -> TraceResult:
    """One wall along y = 0.25, one portal along y = 0.75, one light in the middle."""
    return TraceResult(
        walls=[Wall(points=[Point(fx=0.1, fy=0.25), Point(fx=0.9, fy=0.25)])],
        portals=[Portal(a=Point(fx=0.1, fy=0.75), b=Point(fx=0.9, fy=0.75))],
        lights=[Light(at=Point(fx=0.5, fy=0.5), tier="small")],
        kind="quick",
        model_id="m",
        effort="medium",
        elapsed_s=1.0,
        usage=Usage(),
        cost_usd=0.0,
        traced_size=MapSize(width=10, height=10),
        size_source="typed",
    )


def test_no_result_gives_an_equal_copy():
    """Without a result the preview is the image, as a new object."""
    image = plain()
    out = overlay(image, None)
    assert out is not image and out.tobytes() == image.tobytes()


def test_walls_portals_and_lights_are_drawn_in_three_colors():
    """Pixels on each drawn item change, and the three use different colors."""
    image = plain()
    out = overlay(image, result())
    wall, portal = out.getpixel((200, 100)), out.getpixel((200, 300))
    ring = out.getpixel((200 + 12, 200))  # light ring radius: 0.3 square = 12 px
    assert len({wall, portal, ring, (90, 90, 90)}) == 4


def test_input_is_not_modified_and_size_is_kept():
    """Drawing works on a copy of the same size."""
    image = plain()
    before = image.tobytes()
    out = overlay(image, result())
    assert image.tobytes() == before and out.size == image.size
