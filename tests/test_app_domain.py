"""Domain models and the conversions between grid squares, image fractions and pixels."""

import math

import pytest
from pydantic import ValidationError

from app.domain import (
    MapSize,
    Point,
    Portal,
    RawAnswer,
    answer_to_fractions,
    to_grid,
    to_pixels,
)


def answer(**parts) -> RawAnswer:
    """A RawAnswer from keyword parts, the rest empty."""
    return RawAnswer.model_validate(parts)


def test_grid_point_becomes_fractions_on_a_square_map():
    """Grid (5, 5) on a 10 x 10 map of a 700 x 700 image is the middle."""
    raw = answer(lights=[{"x": 5, "y": 5, "tier": "small"}])
    _, _, lights = answer_to_fractions(raw, MapSize(width=10, height=10), (700, 700))
    assert (lights[0].at.fx, lights[0].at.fy) == (0.5, 0.5)


def test_y_uses_the_views_pixels_per_square_not_the_map_height():
    """On a 700 x 1400 image traced as 10 x 10, grid y = 10 is half way down (R2)."""
    raw = answer(lights=[{"x": 5, "y": 10, "tier": "small"}])
    _, _, lights = answer_to_fractions(raw, MapSize(width=10, height=10), (700, 1400))
    assert lights[0].at.fy == 0.5


def test_values_just_outside_the_image_are_clamped():
    """A point a hair past the border is clamped to 0..1."""
    assert Point(fx=-0.01, fy=1.02) == Point(fx=0.0, fy=1.0)


def test_an_arc_becomes_a_polyline():
    """An arc arrives as a wall with many points on the circle."""
    raw = answer(arcs=[{"cx": 5, "cy": 5, "r": 2, "start_deg": 0, "end_deg": 90}])
    walls, _, _ = answer_to_fractions(raw, MapSize(width=10, height=10), (100, 100))
    assert len(walls) == 1 and len(walls[0].points) > 2
    for p in walls[0].points:
        assert math.isclose(math.hypot(p.fx * 10 - 5, p.fy * 10 - 5), 2)


def test_a_one_point_wall_is_dropped():
    """A wall with a single point is not a wall."""
    raw = answer(walls=[{"points": [{"x": 1, "y": 1}]}])
    walls, _, _ = answer_to_fractions(raw, MapSize(width=10, height=10), (100, 100))
    assert walls == []


@pytest.mark.parametrize("bad", [0, 201, 2.5])
def test_map_size_out_of_range_fails(bad):
    """Map sides are whole numbers from 1 to 200."""
    with pytest.raises(ValidationError):
        MapSize(width=bad, height=10)


def test_portal_with_equal_ends_fails():
    """A portal needs two different ends."""
    with pytest.raises(ValidationError):
        Portal(a=Point(fx=0.1, fy=0.1), b=Point(fx=0.1, fy=0.1))


def test_to_grid_round_trips_answer_to_fractions():
    """On a square-cell map, fractions go back to the grid squares they came from."""
    size = MapSize(width=20, height=10)
    raw = answer(portals=[{"x1": 3, "y1": 4, "x2": 5.5, "y2": 4}])
    _, portals, _ = answer_to_fractions(raw, size, (1400, 700))
    assert to_grid(portals[0].a, size) == pytest.approx((3, 4))
    assert to_grid(portals[0].b, size) == pytest.approx((5.5, 4))


def test_to_pixels_scales_by_the_image_size():
    """Fractions become pixels on the given image."""
    assert to_pixels(Point(fx=0.25, fy=0.5), (400, 200)) == (100, 100)
