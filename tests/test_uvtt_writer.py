"""The .dd2vtt writer: an answer in grid squares becomes a file the rasterizer reads back."""

import json
import math

from data.rasterize import LIGHT, PORTAL, WALL, load_uvtt, parse_lights, rasterize_mask
from postprocess.uvtt import answer_to_uvtt, arc_points, write_uvtt

ANSWER = {
    "walls": [
        {"points": [{"x": 1, "y": 1}, {"x": 4, "y": 1}]},
        {"points": [{"x": 5, "y": 1}, {"x": 9, "y": 1}, {"x": 9, "y": 9}]},
        {"points": [{"x": 2, "y": 2}]},  # a single point is not a wall
    ],
    "arcs": [{"cx": 5, "cy": 5, "r": 2, "start_deg": 0, "end_deg": 90}],
    "portals": [{"x1": 4, "y1": 1, "x2": 5, "y2": 1}],
    "lights": [{"x": 3, "y": 6, "tier": "medium"}],
}


def test_arc_points_lie_on_the_circle_and_run_east_to_south():
    """Arc points sit on the circle, from east (0 degrees) toward south (90)."""
    points = arc_points(5, 5, 2, 0, 90)
    assert all(math.isclose(math.hypot(p["x"] - 5, p["y"] - 5), 2) for p in points)
    assert (points[0]["x"], points[0]["y"]) == (7, 5)  # 0 degrees is east
    assert math.isclose(points[-1]["x"], 5, abs_tol=1e-9)
    assert math.isclose(points[-1]["y"], 7)  # 90 degrees is south: y grows down


def test_answer_becomes_uvtt_with_walls_portals_and_lights():
    """An answer becomes walls, a portal and a light; a one-point wall is dropped."""
    uvtt = answer_to_uvtt(ANSWER, (10, 10))
    assert uvtt["resolution"]["map_size"] == {"x": 10, "y": 10}
    assert len(uvtt["line_of_sight"]) == 3  # two polylines and one arc; the single point is dropped
    assert uvtt["portals"][0]["position"] == {"x": 4.5, "y": 1}
    assert parse_lights(uvtt) == [(3, 6, "medium")]


def test_rasterized_answer_has_every_class_and_the_portal_replaces_the_wall_gap():
    """Rasterized, the answer has every class, with the portal filling the wall's gap."""
    mask = rasterize_mask(answer_to_uvtt(ANSWER, (10, 10)), 32)
    assert mask.shape == (320, 320)
    assert mask[32, 2 * 32] == WALL
    assert mask[32, int(4.5 * 32)] == PORTAL
    assert mask[6 * 32, 3 * 32] == LIGHT


def test_written_file_is_read_back(tmp_path):
    """A written file reads back unchanged."""
    uvtt = answer_to_uvtt(ANSWER, (10, 10), image_bytes=b"not a real image")
    write_uvtt(tmp_path / "map.dd2vtt", uvtt)
    assert load_uvtt(tmp_path / "map.dd2vtt") == json.loads(json.dumps(uvtt))


def test_default_light_table_writes_the_label_ranges():
    """Without a table, a medium light gets range 12 and intensity 1, as before."""
    light = answer_to_uvtt(ANSWER, (10, 10))["lights"][0]
    assert (light["range"], light["intensity"]) == (12.0, 1)


def test_custom_light_table_sets_range_and_intensity():
    """A table passed in decides the written range and intensity."""
    table = {t: {"range": 5.0, "intensity": 0.5} for t in ("small", "medium", "large")}
    light = answer_to_uvtt(ANSWER, (10, 10), lights=table)["lights"][0]
    assert (light["range"], light["intensity"]) == (5.0, 0.5)
