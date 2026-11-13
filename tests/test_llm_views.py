"""Views sent to Claude: crop size, zoom and the answer overlay."""

import numpy as np
from PIL import Image

from llm.views import MARGIN, clamp_box, render_view, to_image_block
from postprocess.uvtt import answer_to_uvtt


def gray_map(squares: int = 10, ppg: int = 70) -> Image.Image:
    return Image.new("RGB", (squares * ppg, squares * ppg), (120, 120, 120))


def test_clamp_box_stays_inside_the_map_and_keeps_one_square():
    assert clamp_box((-3, 2, 50, 4), (10, 10)) == (0, 2, 10, 4)
    assert clamp_box((5, 5, 5, 5), (10, 10)) == (5, 5, 6, 6)
    assert clamp_box((8, 9, 2, 1), (10, 10)) == (2, 1, 8, 9)  # corners in any order


def test_view_is_zoomed_to_the_pixel_budget_plus_margin():
    view, zoom = render_view(gray_map(), 70, (0, 0, 10, 10), max_px=500, max_zoom=160)
    assert zoom == 50
    assert view.size == (500 + MARGIN, 500 + MARGIN)


def test_small_window_is_capped_at_max_zoom():
    view, zoom = render_view(gray_map(), 70, (2, 2, 4, 3), max_px=1300, max_zoom=160)
    assert zoom == 160
    assert view.size == (320 + MARGIN, 160 + MARGIN)


def test_overlay_draws_the_wall_in_red():
    answer = {"walls": [{"points": [{"x": 1, "y": 5.5}, {"x": 9, "y": 5.5}]}]}
    uvtt = answer_to_uvtt(answer, (10, 10))
    plain, zoom = render_view(gray_map(), 70, (0, 0, 10, 10), max_px=500)
    drawn, _ = render_view(gray_map(), 70, (0, 0, 10, 10), max_px=500, uvtt=uvtt)
    at = (MARGIN + round(5.5 * zoom), MARGIN + round(5.3 * zoom))  # (row, column) on the wall
    r, g, b = np.array(drawn)[at]
    assert r > 200 and g < 100 and b < 100
    assert tuple(np.array(plain)[at]) == (120, 120, 120)


def test_image_block_is_base64_jpeg():
    block = to_image_block(gray_map(2))
    assert block["type"] == "image"
    assert block["source"]["media_type"] == "image/jpeg"
    assert block["source"]["data"].startswith("/9j/")  # JPEG magic bytes in base64
