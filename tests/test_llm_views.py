"""Views sent to Claude: crop size, zoom and the answer overlay."""

import numpy as np
from PIL import Image

from llm.views import MARGIN, OUTLINE_RGB, clamp_box, render_view, to_image_block
from postprocess.uvtt import answer_to_uvtt


def gray_map(squares: int = 10, ppg: int = 70) -> Image.Image:
    """A plain grey map of `squares` x `squares` at `ppg` pixels per square."""
    return Image.new("RGB", (squares * ppg, squares * ppg), (120, 120, 120))


def test_clamp_box_stays_inside_the_map_and_keeps_one_square():
    """A window is clamped to the map, kept one square or more, its corners in any order."""
    assert clamp_box((-3, 2, 50, 4), (10, 10)) == (0, 2, 10, 4)
    assert clamp_box((5, 5, 5, 5), (10, 10)) == (5, 5, 6, 6)
    assert clamp_box((8, 9, 2, 1), (10, 10)) == (2, 1, 8, 9)  # corners in any order


def test_view_is_zoomed_to_the_pixel_budget_plus_margin():
    """The whole 10-square map fits the 500 px budget at 50 px per square, plus the label margin."""
    view, zoom = render_view(gray_map(), 70, (0, 0, 10, 10), max_px=500, max_zoom=160)
    assert zoom == 50
    assert view.size == (500 + MARGIN, 500 + MARGIN)


def test_small_window_is_capped_at_max_zoom():
    """A small window is not zoomed past max_zoom."""
    view, zoom = render_view(gray_map(), 70, (2, 2, 4, 3), max_px=1300, max_zoom=160)
    assert zoom == 160
    assert view.size == (320 + MARGIN, 160 + MARGIN)


def test_overlay_draws_the_wall_in_red():
    """An answer overlay draws its wall in red where the plain view is grey."""
    answer = {"walls": [{"points": [{"x": 1, "y": 5.5}, {"x": 9, "y": 5.5}]}]}
    uvtt = answer_to_uvtt(answer, (10, 10))
    plain, zoom = render_view(gray_map(), 70, (0, 0, 10, 10), max_px=500)
    drawn, _ = render_view(gray_map(), 70, (0, 0, 10, 10), max_px=500, uvtt=uvtt)
    at = (MARGIN + round(5.5 * zoom), MARGIN + round(5.3 * zoom))  # (row, column) on the wall
    r, g, b = np.array(drawn)[at]
    assert r > 200 and g < 100 and b < 100
    assert tuple(np.array(plain)[at]) == (120, 120, 120)


def test_image_block_is_base64_jpeg():
    """An image block is a base64 JPEG for the Messages API."""
    block = to_image_block(gray_map(2))
    assert block["type"] == "image"
    assert block["source"]["media_type"] == "image/jpeg"
    assert block["source"]["data"].startswith("/9j/")  # JPEG magic bytes in base64


def test_outline_and_strips_default_to_the_same_image():
    """Leaving `outline` and `strips` unset draws exactly what render_view drew before."""
    before, _ = render_view(gray_map(), 70, (0, 0, 10, 10), max_px=500)
    after, _ = render_view(gray_map(), 70, (0, 0, 10, 10), max_px=500, outline=None, strips=None)
    assert before.tobytes() == after.tobytes()


def test_outline_marks_the_rectangle_border_only():
    """The chunk outline is drawn on the box's edge in OUTLINE_RGB; its inside is untouched."""
    view, zoom = render_view(gray_map(), 70, (0, 0, 10, 10), max_px=500, outline=(2, 2, 8, 8))
    pixels = np.array(view)
    edge = (MARGIN + round(5.3 * zoom), MARGIN + round(2 * zoom))  # (row, column) on x = 2
    inside = (MARGIN + round(5.3 * zoom), MARGIN + round(5.3 * zoom))
    assert tuple(pixels[edge]) == OUTLINE_RGB
    assert tuple(pixels[inside]) == (120, 120, 120)


def test_strips_tint_only_inside_the_band():
    """A seam strip is a translucent amber band: pixels inside change, pixels outside do not."""
    view, zoom = render_view(gray_map(), 70, (0, 0, 10, 10), max_px=500, strips=[(4.5, 0, 6.5, 10)])
    pixels = np.array(view).astype(int)
    inside = pixels[MARGIN + round(2.3 * zoom), MARGIN + round(5.3 * zoom)]
    outside = pixels[MARGIN + round(2.3 * zoom), MARGIN + round(8.3 * zoom)]
    assert inside[0] > 120 and inside[2] < 120  # warmer: more red, less blue
    assert tuple(outside) == (120, 120, 120)
