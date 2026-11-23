"""The chunked pass's geometry (`llm/merge.py`): chunk layout, clipping, the rule-based merge,
seams, applying the seam review, and the seam checks. Pure functions, no model."""

import math
import random
from pathlib import Path

import pytest

from data.rasterize import light_tier, load_uvtt, rasterize_mask
from eval.metrics import portal_recall, score
from llm.merge import (
    apply_review,
    chunk_layout,
    clip_polyline,
    clip_polyline_outside,
    merge_answers,
    owner,
    seam_checks,
    seams,
)
from postprocess.uvtt import answer_to_uvtt

from conftest import DEMO_MAP

REFERENCE_CASTLE = Path(__file__).parents[1] / "data" / "reference" / "dd07_a.dd2vtt"
TOL, PIECE = 0.3, 0.05


def layout(w: int = 25, h: int = 25):
    """The default layout (13-square cores, 1-square overlap, at most 4 per side)."""
    return chunk_layout((w, h), core_squares=13, overlap_squares=1, max_per_side=4)


def wall(*points) -> dict:
    """A wall in answer form from (x, y) pairs."""
    return {"points": [{"x": x, "y": y} for x, y in points]}


def points_of(answer: dict) -> list[list[tuple[float, float]]]:
    """Every wall of an answer as a list of (x, y) tuples."""
    return [[(p["x"], p["y"]) for p in w["points"]] for w in answer["walls"]]


# --- Layout (T007) ---------------------------------------------------------------------------


@pytest.mark.parametrize("size", [(1, 1), (13, 13), (25, 25), (27, 14), (50, 50), (200, 200)])
def test_cores_partition_the_map(size):
    """Every point lies in exactly one core: half-open intervals, closed at the map edge."""
    chunks = layout(*size)
    rng = random.Random(7)
    w, h = size
    points = [(rng.uniform(0, w), rng.uniform(0, h)) for _ in range(500)]
    points += [(0, 0), (w, h), (w, 0), (0, h)]
    points += [(c.core[2], c.core[3]) for c in chunks]  # inner corners belong to one core

    def inside(chunk, x, y):
        """Half-open on the right and bottom, closed at the map's own right and bottom edge."""
        x0, y0, x1, y1 = chunk.core
        in_x = x0 <= x < x1 or (x == x1 == w)
        in_y = y0 <= y < y1 or (y == y1 == h)
        return in_x and in_y

    for x, y in points:
        assert sum(inside(c, x, y) for c in chunks) == 1
        assert inside(chunks[owner(x, y, chunks)], x, y)


@pytest.mark.parametrize(
    ("size", "grid"),
    [
        ((1, 1), (1, 1)),
        ((13, 13), (1, 1)),
        ((25, 25), (2, 2)),
        ((27, 14), (3, 2)),
        ((50, 50), (4, 4)),
        ((200, 200), (4, 4)),
        ((200, 10), (4, 1)),
    ],
)
def test_chunk_count_is_capped_at_four_per_side(size, grid):
    """nx = min(ceil(W / core_squares), max_per_side), likewise ny; never more than 16."""
    chunks = layout(*size)
    assert (max(c.col for c in chunks) + 1, max(c.row for c in chunks) + 1) == grid
    assert len(chunks) <= 16


def test_25_by_25_gives_four_equal_cores_and_overlapping_windows():
    """The reference size: 2 x 2 cores of 12.5 squares, windows reaching 1 square across."""
    chunks = layout()
    assert [c.core for c in chunks] == [
        (0, 0, 12.5, 12.5),
        (12.5, 0, 25, 12.5),
        (0, 12.5, 12.5, 25),
        (12.5, 12.5, 25, 25),
    ]
    assert chunks[0].window == (0, 0, 13.5, 13.5)
    assert chunks[3].window == (11.5, 11.5, 25, 25)
    assert [(c.index, c.col, c.row) for c in chunks] == [(0, 0, 0), (1, 1, 0), (2, 0, 1), (3, 1, 1)]


def test_one_chunk_is_the_whole_map():
    """A map no larger than one chunk: core and window are the map."""
    (chunk,) = layout(13, 13)
    assert chunk.core == chunk.window == (0, 0, 13, 13)


@pytest.mark.parametrize("size", [(25, 25), (27, 14), (50, 50)])
def test_windows_hold_their_cores_and_stay_on_the_map(size):
    """A window contains its core, reaches 1 square past every inner border, and is clipped."""
    w, h = size
    for c in layout(*size):
        cx0, cy0, cx1, cy1 = c.core
        wx0, wy0, wx1, wy1 = c.window
        assert wx0 == max(0, cx0 - 1) and wy0 == max(0, cy0 - 1)
        assert wx1 == min(w, cx1 + 1) and wy1 == min(h, cy1 + 1)


# --- Clipping (T009) -------------------------------------------------------------------------


def test_clip_keeps_a_polyline_inside_the_box():
    """A polyline fully inside is returned whole, as one piece."""
    assert clip_polyline([(1, 1), (3, 1), (3, 3)], (0, 0, 5, 5)) == [[(1, 1), (3, 1), (3, 3)]]


def test_clip_cuts_exactly_on_the_edge():
    """A segment crossing the box edge is cut on it."""
    assert clip_polyline([(1, 2), (9, 2)], (0, 0, 5, 5)) == [[(1, 2), (5, 2)]]


def test_clip_leaving_and_reentering_gives_two_pieces():
    """Out and back in: two pieces."""
    pieces = clip_polyline([(1, 1), (8, 1), (8, 4), (1, 4)], (0, 0, 5, 5))
    assert pieces == [[(1, 1), (5, 1)], [(5, 4), (1, 4)]]


def test_clip_drops_a_polyline_outside():
    """Nothing inside, nothing returned."""
    assert clip_polyline([(6, 6), (9, 9)], (0, 0, 5, 5)) == []


def test_clip_keeps_a_segment_lying_on_the_edge_once():
    """A segment along the box edge counts as inside, once."""
    assert clip_polyline([(5, 1), (5, 4)], (0, 0, 5, 5)) == [[(5, 1), (5, 4)]]


def test_clip_outside_removes_the_union_of_boxes():
    """The parts outside two overlapping boxes, cut exactly on their edges."""
    pieces = clip_polyline_outside([(0, 2), (20, 2)], [(4, 0, 8, 5), (6, 0, 10, 5)])
    assert pieces == [[(0, 2), (4, 2)], [(10, 2), (20, 2)]]


def test_clip_outside_keeps_a_polyline_clear_of_the_boxes():
    """A polyline that never touches a box is returned whole."""
    assert clip_polyline_outside([(0, 8), (3, 8), (3, 9)], [(4, 0, 8, 5)]) == [
        [(0, 8), (3, 8), (3, 9)]
    ]


# --- Merge (T011) ----------------------------------------------------------------------------


def test_a_wall_across_a_seam_comes_out_as_one_polyline():
    """Both left-hand neighbours trace the wall across x = 12.5; its two halves meet 0.2
    apart on the seam and are joined into one wall."""
    chunks = layout()
    answers = {
        0: {"walls": [wall((3, 5), (13.5, 5.1))]},
        1: {"walls": [wall((11.5, 4.9), (22, 5))]},
    }
    merged, report = merge_answers(chunks, answers, (25, 25), TOL, PIECE)
    (line,) = points_of(merged)
    assert line[0] == (3, 5) and line[-1] == (22, 5)
    assert any(math.isclose(x, 12.5) for x, _ in line)
    assert report.joins == 1 and report.ends_snapped == 2


def test_four_walls_meeting_at_the_corner_share_one_point_and_stay_separate():
    """At the point where four chunks meet, the four ends are snapped together, not joined."""
    chunks = layout()
    answers = {
        0: {"walls": [wall((10, 10), (13, 13))]},
        1: {"walls": [wall((15, 10), (12, 13))]},
        2: {"walls": [wall((10, 15), (13, 12))]},
        3: {"walls": [wall((15, 15), (12, 12))]},
    }
    merged, report = merge_answers(chunks, answers, (25, 25), TOL, PIECE)
    lines = points_of(merged)
    ends = {line[i] for line in lines for i in (0, -1)}
    inner = [p for p in ends if math.dist(p, (12.5, 12.5)) < TOL]
    assert len(set(inner)) == 1
    assert report.joins == 0


def test_a_door_and_a_light_in_the_overlap_come_out_once():
    """Ownership: the chunk whose core holds the midpoint keeps it; the other's copy drops."""
    chunks = layout()
    door = {"x1": 11.8, "y1": 6, "x2": 12.2, "y2": 6}  # midpoint (12.0, 6): chunk 0's core
    light = {"x": 13, "y": 3, "tier": "small"}  # chunk 1's core
    answers = {0: {"portals": [door], "lights": [light]}, 1: {"portals": [door], "lights": [light]}}
    merged, report = merge_answers(chunks, answers, (25, 25), TOL, PIECE)
    assert merged["portals"] == [door] and merged["lights"] == [light]
    assert report.portals_kept == [1, 0, 0, 0] and report.portals_dropped == [0, 1, 0, 0]
    assert report.lights_kept == [0, 1, 0, 0] and report.lights_dropped == [1, 0, 0, 0]


def test_a_wall_ending_on_a_seam_alone_is_not_moved_or_extended():
    """No partner within the tolerance: the end stays where the clip put it."""
    chunks = layout()
    answers = {0: {"walls": [wall((3, 8), (14, 8))]}, 1: {"walls": [wall((12.5, 2), (20, 2))]}}
    merged, _ = merge_answers(chunks, answers, (25, 25), TOL, PIECE)
    lines = sorted(points_of(merged))
    assert lines == [[(3, 8), (12.5, 8)], [(12.5, 2), (20, 2)]]


def test_short_clipped_pieces_are_dropped_and_counted():
    """A sliver under min_piece left by the clip is dropped."""
    chunks = layout()
    answers = {0: {"walls": [wall((12.49, 3), (12.49, 3.03), (13, 3.03))]}}
    merged, report = merge_answers(chunks, answers, (25, 25), TOL, PIECE)
    assert merged["walls"] == [] and report.pieces_dropped == 1


def test_a_wall_lying_on_a_seam_is_kept_once():
    """Both neighbours trace the same wall exactly along x = 12.5: it is not doubled."""
    chunks = layout()
    answers = {
        0: {"walls": [wall((12.5, 2), (12.5, 8))]},
        1: {"walls": [wall((12.5, 2), (12.5, 8))]},
    }
    merged, _ = merge_answers(chunks, answers, (25, 25), TOL, PIECE)
    assert points_of(merged) == [[(12.5, 2), (12.5, 8)]]


def test_an_arc_across_a_seam_is_joined_like_a_wall():
    """An arc spanning the seam (traced by both sides) comes out as one connected polyline."""
    chunks = layout()
    arc = {"cx": 12.5, "cy": 6, "r": 3, "start_deg": 180, "end_deg": 360}
    answers = {0: {"arcs": [arc]}, 1: {"arcs": [arc]}}
    merged, _ = merge_answers(chunks, answers, (25, 25), TOL, PIECE)
    (line,) = points_of(merged)
    assert math.dist(line[0], (9.5, 6)) < 1e-6 and math.dist(line[-1], (15.5, 6)) < 1e-6
    assert "arcs" not in merged


def test_merge_is_deterministic_and_stays_on_the_map():
    """Same input, same output; no point leaves the map even when an agent drew past it."""
    chunks = layout()
    answers = {
        1: {"walls": [wall((14, 3), (26, 3))]},
        3: {"walls": [wall((20, 20), (20, 25.4))], "lights": [{"x": 24, "y": 24, "tier": "large"}]},
    }
    first = merge_answers(chunks, answers, (25, 25), TOL, PIECE)
    second = merge_answers(chunks, answers, (25, 25), TOL, PIECE)
    assert first[0] == second[0]
    for line in points_of(first[0]):
        assert all(0 <= x <= 25 and 0 <= y <= 25 for x, y in line)


def test_one_chunk_returns_its_answer():
    """A one-chunk map: the merge is the answer, with arcs as polylines."""
    chunks = layout(13, 13)
    answer = {
        "walls": [wall((1, 1), (12, 1))],
        "arcs": [{"cx": 6, "cy": 6, "r": 2, "start_deg": 0, "end_deg": 90}],
        "portals": [{"x1": 2, "y1": 1, "x2": 3, "y2": 1}],
        "lights": [{"x": 4, "y": 4, "tier": "medium"}],
    }
    merged, report = merge_answers(chunks, {0: answer}, (13, 13), TOL, PIECE)
    assert len(merged["walls"]) == 2 and merged["portals"] == answer["portals"]
    assert merged["lights"] == answer["lights"] and "arcs" not in merged
    assert report.walls_in == 2 and report.walls_out == 2


# --- The merge loses nothing on real labels (T013, quickstart step 2) ------------------------


def label_answer(uvtt: dict) -> dict:
    """A label file's walls, portals and lights in answer form."""
    walls = [
        {"points": [{"x": p["x"], "y": p["y"]} for p in line]}
        for line in uvtt["line_of_sight"] + uvtt.get("objects_line_of_sight", [])
    ]
    portals = []
    for p in uvtt["portals"]:
        a, b = p["bounds"]
        portals.append({"x1": a["x"], "y1": a["y"], "x2": b["x"], "y2": b["y"]})
    lights = [
        {"x": li["position"]["x"], "y": li["position"]["y"], "tier": light_tier(li["range"])}
        for li in uvtt["lights"]
    ]
    return {"walls": walls, "portals": portals, "lights": lights}


def cut_to_window(answer: dict, window) -> dict:
    """What a perfect agent for `window` would report: the label's parts inside its window."""
    x0, y0, x1, y1 = window

    def inside(x, y):
        """Whether a point lies in the window."""
        return x0 <= x <= x1 and y0 <= y <= y1

    walls = []
    for w in answer["walls"]:
        for piece in clip_polyline([(p["x"], p["y"]) for p in w["points"]], window):
            walls.append({"points": [{"x": x, "y": y} for x, y in piece]})
    portals = [
        p for p in answer["portals"] if inside((p["x1"] + p["x2"]) / 2, (p["y1"] + p["y2"]) / 2)
    ]
    lights = [li for li in answer["lights"] if inside(li["x"], li["y"])]
    return {"walls": walls, "portals": portals, "lights": lights}


@pytest.mark.parametrize("path", [DEMO_MAP, REFERENCE_CASTLE], ids=["demo", "castle"])
def test_merging_a_label_cut_into_chunks_loses_nothing(path):
    """Four perfect agents' answers, merged, score as the label itself (SC-003)."""
    label = load_uvtt(path)
    size = (label["resolution"]["map_size"]["x"], label["resolution"]["map_size"]["y"])
    chunks = layout(*size)
    truth = label_answer(label)
    answers = {c.index: cut_to_window(truth, c.window) for c in chunks}
    merged, _ = merge_answers(chunks, answers, size, TOL, PIECE)
    pred = answer_to_uvtt(merged, size)
    want = answer_to_uvtt(truth, size)
    scores = score(rasterize_mask(pred, 32), rasterize_mask(want, 32), 32)
    assert scores["boundary_f1_wall"] >= 0.99
    assert portal_recall(pred, want) == 1.0
    assert len(merged["portals"]) == len(truth["portals"])
    assert len(merged["lights"]) == len(truth["lights"])


# --- Seams (T016) ----------------------------------------------------------------------------


def test_seams_of_a_two_by_two_layout():
    """Two seams, x = 12.5 and y = 12.5, each with a 2-square strip the map's length."""
    found = seams(layout(), (25, 25), strip_squares=1.0)
    assert [(s.axis, s.at, s.strip) for s in found] == [
        ("x", 12.5, (11.5, 0, 13.5, 25)),
        ("y", 12.5, (0, 11.5, 25, 13.5)),
    ]


def test_seams_count_and_clipping():
    """(nx - 1) + (ny - 1) seams; none for one chunk; strips stay on the map."""
    assert len(seams(layout(27, 14), (27, 14), 1.0)) == 3
    assert seams(layout(13, 13), (13, 13), 1.0) == []
    for s in seams(layout(4, 30), (4, 30), 5.0):
        x0, y0, x1, y1 = s.strip
        assert 0 <= x0 and 0 <= y0 and x1 <= 4 and y1 <= 30


# --- Applying the review (T018) and the seam checks ------------------------------------------


STRIPS = [(11.5, 0, 13.5, 25), (0, 11.5, 25, 13.5)]


def test_review_changes_nothing_outside_the_strips():
    """Every merged point, portal and light outside the strips survives; nothing the review
    submits outside them gets in."""
    merged = {
        "walls": [wall((3, 5), (22, 5)), wall((5, 20), (8, 20))],
        "portals": [{"x1": 4, "y1": 5, "x2": 5, "y2": 5}, {"x1": 12, "y1": 5, "x2": 13, "y2": 5}],
        "lights": [{"x": 20, "y": 20, "tier": "small"}, {"x": 12.5, "y": 8, "tier": "small"}],
    }
    submission = {
        "walls": [wall((11.5, 5.1), (13.5, 5.1)), wall((2, 2), (6, 2))],
        "portals": [{"x1": 1, "y1": 1, "x2": 2, "y2": 1}],
        "lights": [{"x": 2, "y": 2, "tier": "large"}, {"x": 12.6, "y": 9, "tier": "small"}],
    }
    final, removed, added = apply_review(merged, submission, STRIPS, (25, 25), TOL, PIECE)
    assert [(5, 20), (8, 20)] in points_of(final)
    assert {"x1": 4, "y1": 5, "x2": 5, "y2": 5} in final["portals"]
    assert {"x1": 12, "y1": 5, "x2": 13, "y2": 5} not in final["portals"]
    assert {"x1": 1, "y1": 1, "x2": 2, "y2": 1} not in final["portals"]
    assert {"x": 20, "y": 20, "tier": "small"} in final["lights"]
    assert {"x": 2, "y": 2, "tier": "large"} not in final["lights"]
    assert {"x": 12.6, "y": 9, "tier": "small"} in final["lights"]
    for line in points_of(final):
        assert (2, 2) not in line
    assert removed == {"walls": 1, "portals": 1, "lights": 1}
    assert added == {"walls": 1, "portals": 0, "lights": 1}


def test_a_submitted_wall_is_joined_to_the_merged_wall_at_the_strip_edges():
    """The wall across x = 12.5 is replaced inside the strip and joined back into one line."""
    merged = {"walls": [wall((3, 5), (22, 5))], "portals": [], "lights": []}
    submission = {"walls": [wall((11.5, 5.1), (12.5, 5.1), (13.5, 5.1))]}
    final, _, _ = apply_review(merged, submission, STRIPS, (25, 25), TOL, PIECE)
    (line,) = points_of(final)
    assert line[0] == (3, 5) and line[-1] == (22, 5)
    assert any(math.isclose(y, 5.1) for _, y in line)


def test_an_empty_submission_clears_the_strips_and_nothing_else():
    """Nothing submitted: the strips' content goes, everything else stays."""
    merged = {"walls": [wall((3, 5), (22, 5))], "portals": [], "lights": []}
    final, removed, added = apply_review(merged, {}, STRIPS, (25, 25), TOL, PIECE)
    assert sorted(points_of(final)) == [[(3, 5), (11.5, 5)], [(13.5, 5), (22, 5)]]
    assert removed["walls"] == 1 and added == {"walls": 0, "portals": 0, "lights": 0}


def test_seam_checks_count_gaps_and_duplicates():
    """An end on a seam with nothing within 0.1 is a gap; two walls meeting are not; portals
    or lights closer than 0.5 are duplicates."""
    found = seams(layout(), (25, 25), 1.0)
    answer = {
        "walls": [
            wall((3, 5), (12.5, 5)),
            wall((12.5, 5.4), (22, 5.4)),
            wall((3, 8), (12.5, 8)),
            wall((12.5, 8), (20, 8)),
        ],
        "portals": [{"x1": 4, "y1": 5, "x2": 5, "y2": 5}, {"x1": 4.2, "y1": 5, "x2": 5.2, "y2": 5}],
        "lights": [{"x": 2, "y": 2, "tier": "small"}, {"x": 9, "y": 9, "tier": "small"}],
    }
    checks = seam_checks(answer, found, gap=0.1, same=0.5)
    assert checks == {"seam_gap_ends": 2, "duplicate_portals": 1, "duplicate_lights": 0}


def covered(answer: dict, y: float, x0: float, x1: float) -> bool:
    """Whether any horizontal wall at height `y` runs over part of the open interval x0..x1."""
    for line in points_of(answer):
        for (ax, ay), (bx, by) in zip(line, line[1:], strict=False):
            if abs(ay - y) < 1e-6 and abs(by - y) < 1e-6:
                lo, hi = sorted((ax, bx))
                if hi > x0 + 1e-6 and lo < x1 - 1e-6:
                    return True
    return False


def test_a_door_gap_just_beside_a_seam_stays_open():
    """FR-008: a door from 11.6 to 12.4 (left of x = 12.5), traced by both neighbours, keeps
    its gap; the wall to its right is joined across the seam; the door comes out once."""
    chunks = layout()
    door = {"x1": 11.6, "y1": 6, "x2": 12.4, "y2": 6}
    left, right = wall((3, 6), (11.6, 6)), wall((12.4, 6), (22, 6))
    answers = {
        0: {"walls": [left, wall((12.4, 6), (13.5, 6))], "portals": [door]},
        1: {"walls": [wall((11.5, 6), (11.6, 6)), right], "portals": [door]},
    }
    merged, _ = merge_answers(chunks, answers, (25, 25), TOL, PIECE)
    assert not covered(merged, 6, 11.6, 12.4)
    assert merged["portals"] == [door]
    assert [(12.4, 6), (12.5, 6), (22, 6)] in points_of(merged)


def test_a_door_straddling_a_seam_stays_open():
    """A door across x = 12.5 keeps its gap and is kept once, by the part owning its middle."""
    chunks = layout()
    door = {"x1": 12.2, "y1": 6, "x2": 12.8, "y2": 6}
    walls = [wall((3, 6), (12.2, 6)), wall((12.8, 6), (22, 6))]
    answers = {0: {"walls": walls, "portals": [door]}, 1: {"walls": walls, "portals": [door]}}
    merged, report = merge_answers(chunks, answers, (25, 25), TOL, PIECE)
    assert not covered(merged, 6, 12.2, 12.8)
    assert merged["portals"] == [door] and report.portals_kept == [0, 1, 0, 0]
