"""The chunked pass's geometry: chunk layout, clipping, the rule-based merge, seams, applying the
seam review, and the seam checks. Pure functions; no model call anywhere in this module.

All coordinates are whole-map grid squares (origin top-left, y down), as in every answer.
Design: specs/002-chunked-map-tracing/research.md R2 (layout), R4 (merge), R6 (review).

The merge works by **ownership**: the cores of a layout partition the map, each chunk keeps
only the parts of its answer that lie in its own core, so an item two agents both report in
their overlap is kept once without any matching. Inner borders sit at quarter squares (x.25,
x.75), off the whole and half squares where grid-aligned walls are drawn. Then, along every
seam: a wall both neighbours drew along it is kept once, and wall ends near it are paired
one to one across it (closest first, never through a door) and joined.

Revised 23.11 after live Haiku runs showed walls lost or doubled along seams and wall ends
joined wrongly (specs/002-chunked-map-tracing/research.md R4).
"""

import math
from dataclasses import dataclass, field
from itertools import pairwise

from llm.views import Box
from postprocess.uvtt import arc_points

EPS = 1e-6  # squares: "on a line" and "the same point" for clipped coordinates
Point = tuple[float, float]
Line = list[Point]


@dataclass(frozen=True)
class Chunk:
    """One chunk of a layout: its own area (`core`) and what its agent sees (`window`)."""

    index: int  # 0-based, row by row from the top-left; users see index + 1 ("part 1")
    col: int
    row: int
    core: Box  # the cores of a layout partition the map
    window: Box  # core grown by the overlap on every side with a neighbour, clipped to the map


@dataclass(frozen=True)
class Seam:
    """A border between neighbouring cores, and the strip along it the review may change."""

    axis: str  # "x": a vertical seam at x = at; "y": a horizontal one at y = at
    at: float
    strip: Box


@dataclass
class MergeReport:
    """What the merge did, for the run log and the run folder."""

    walls_in: int = 0  # polylines (walls and arcs) in all chunk answers
    walls_out: int = 0  # polylines after clipping, snapping and joining
    pieces_dropped: int = 0  # clipped pieces shorter than min_piece
    ends_snapped: int = 0  # ends moved onto a seam to meet their partner across it
    joins: int = 0
    walls_deduped: int = 0  # walls along a seam that both neighbours drew, kept once
    portals_kept: list[int] = field(default_factory=list)  # per chunk index
    portals_dropped: list[int] = field(default_factory=list)
    lights_kept: list[int] = field(default_factory=list)
    lights_dropped: list[int] = field(default_factory=list)


# --- Layout ----------------------------------------------------------------------------------


def _off_grid(v: float) -> float:
    """The nearest quarter square (x.25 or x.75) to `v`; a tie goes to the lower one."""
    return math.floor((v - 0.25) * 2 + 0.5 - 1e-9) / 2 + 0.25


def _cuts(length: float, n: int) -> list[float]:
    """`n` nearly equal slices of `length`, as their n + 1 borders.

    Inner borders are moved to the nearest quarter square, so a seam never lies on a whole or
    half square, where grid-aligned walls are drawn; slices differ by at most half a square.
    """
    inner = [_off_grid(length * i / n) for i in range(1, n)]
    return [0.0, *inner, float(length)]


def chunk_layout(
    map_size: tuple[int, int], core_squares: float, overlap_squares: float, max_per_side: int
) -> list[Chunk]:
    """Split a map into equal cores, at most `max_per_side` across and down.

    nx = min(ceil(W / core_squares), max_per_side), likewise ny; each side is split evenly, so
    there is no thin last strip, with inner borders at quarter squares (`_cuts`). Each window
    is its core grown by `overlap_squares` on every side that has a neighbour, clipped to the
    map.
    """
    w, h = map_size
    nx = max(1, min(math.ceil(w / core_squares), max_per_side))
    ny = max(1, min(math.ceil(h / core_squares), max_per_side))
    xs, ys = _cuts(w, nx), _cuts(h, ny)
    chunks = []
    for row in range(ny):
        for col in range(nx):
            core = (xs[col], ys[row], xs[col + 1], ys[row + 1])
            window = (
                max(0.0, core[0] - overlap_squares) if col > 0 else core[0],
                max(0.0, core[1] - overlap_squares) if row > 0 else core[1],
                min(float(w), core[2] + overlap_squares) if col < nx - 1 else core[2],
                min(float(h), core[3] + overlap_squares) if row < ny - 1 else core[3],
            )
            chunks.append(Chunk(len(chunks), col, row, core, window))
    return chunks


def _extent(layout: list[Chunk]) -> tuple[float, float]:
    """The map's width and height, from its layout's cores."""
    return max(c.core[2] for c in layout), max(c.core[3] for c in layout)


def owner(x: float, y: float, layout: list[Chunk]) -> int:
    """The index of the chunk whose core holds (x, y).

    Cores are half-open on the right and bottom, closed at the map's own right and bottom
    edge, so every point of the map has exactly one owner. Points a hair off the map are
    clamped onto it first.
    """
    w, h = _extent(layout)
    x, y = min(max(x, 0.0), w), min(max(y, 0.0), h)
    for chunk in layout:
        x0, y0, x1, y1 = chunk.core
        in_x = x0 <= x < x1 or (x == x1 and x1 >= w)
        in_y = y0 <= y < y1 or (y == y1 and y1 >= h)
        if in_x and in_y:
            return chunk.index
    raise ValueError(f"({x}, {y}) is in no core")  # unreachable for a valid layout


# --- Clipping --------------------------------------------------------------------------------


def _segment_in_box(p: Point, q: Point, box: Box) -> tuple[float, float] | None:
    """The parameter interval (t0, t1) of segment p-q inside `box` (Liang-Barsky), or None."""
    x0, y0, x1, y1 = box
    dx, dy = q[0] - p[0], q[1] - p[1]
    t0, t1 = 0.0, 1.0
    for pk, qk in ((-dx, p[0] - x0), (dx, x1 - p[0]), (-dy, p[1] - y0), (dy, y1 - p[1])):
        if pk == 0:
            if qk < 0:
                return None
            continue
        t = qk / pk
        if pk < 0:
            t0 = max(t0, t)
        else:
            t1 = min(t1, t)
    return (t0, t1) if t0 <= t1 else None


def _at(p: Point, q: Point, t: float) -> Point:
    """The point at parameter t on segment p-q; exactly p or q at the ends.

    Cut points are rounded to 1e-9 square, so a cut on a box edge at 13.5 is 13.5 and not
    13.500000000000002; that keeps ends on a seam comparable and output deterministic.
    """
    if t <= 0:
        return p
    if t >= 1:
        return q
    return (round(p[0] + (q[0] - p[0]) * t, 9), round(p[1] + (q[1] - p[1]) * t, 9))


def _union(intervals: list[tuple[float, float]]) -> list[tuple[float, float]]:
    """Merge overlapping parameter intervals; zero-length ones are dropped."""
    out: list[tuple[float, float]] = []
    for t0, t1 in sorted(i for i in intervals if i[1] - i[0] > EPS):
        if out and t0 <= out[-1][1] + EPS:
            out[-1] = (out[-1][0], max(out[-1][1], t1))
        else:
            out.append((t0, t1))
    return out


def _complement(intervals: list[tuple[float, float]]) -> list[tuple[float, float]]:
    """The parts of [0, 1] not covered by merged `intervals`."""
    out, start = [], 0.0
    for t0, t1 in intervals:
        if t0 - start > EPS:
            out.append((start, t0))
        start = t1
    if 1.0 - start > EPS:
        out.append((start, 1.0))
    return out


def _pieces(points: Line, keep) -> list[Line]:
    """Split a polyline into the pieces where `keep(p, q)` gives its kept parameter intervals.

    Consecutive kept parts that meet at a vertex stay one piece.
    """
    pieces: list[Line] = []
    open_piece = False  # whether the last segment's kept part reached its end (t = 1)
    for p, q in pairwise(points):
        for t0, t1 in keep(p, q):
            a, b = _at(p, q, t0), _at(p, q, t1)
            if open_piece and t0 <= EPS:
                pieces[-1].append(b)
            else:
                pieces.append([a, b])
            open_piece = t1 >= 1 - EPS
        if not keep(p, q):
            open_piece = False
    return pieces


def clip_polyline(points: Line, box: Box) -> list[Line]:
    """The pieces of a polyline inside `box`, cut exactly on its edges."""

    def keep(p: Point, q: Point) -> list[tuple[float, float]]:
        """The segment's interval inside the box, if any (a lone touching point is dropped)."""
        found = _segment_in_box(p, q, box)
        if found is None or (found[1] - found[0] <= EPS and p != q):
            return []
        return [found]

    return _pieces(points, keep)


def _inside_any(p: Point, q: Point, boxes: list[Box]) -> list[tuple[float, float]]:
    """The merged parameter intervals of segment p-q inside any of `boxes`."""
    return _union([i for b in boxes if (i := _segment_in_box(p, q, b)) is not None])


def clip_polyline_inside(points: Line, boxes: list[Box]) -> list[Line]:
    """The pieces of a polyline inside the union of `boxes` (each part once)."""
    return _pieces(points, lambda p, q: _inside_any(p, q, boxes))


def clip_polyline_outside(points: Line, boxes: list[Box]) -> list[Line]:
    """The pieces of a polyline outside the union of `boxes`, cut exactly on their edges."""
    return _pieces(points, lambda p, q: _complement(_inside_any(p, q, boxes)))


def _length(line: Line) -> float:
    """A polyline's length in squares."""
    return sum(math.dist(a, b) for a, b in pairwise(line))


# --- Answers ---------------------------------------------------------------------------------


def _lines(answer: dict) -> list[Line]:
    """An answer's walls and arcs as polylines of (x, y) tuples (arcs with r <= 0 dropped)."""
    lines = [
        [(p["x"], p["y"]) for p in w["points"]]
        for w in answer.get("walls", [])
        if len(w["points"]) >= 2
    ]
    for a in answer.get("arcs", []):
        if a["r"] > 0:
            pts = arc_points(a["cx"], a["cy"], a["r"], a["start_deg"], a["end_deg"])
            lines.append([(p["x"], p["y"]) for p in pts])
    return lines


def _walls(lines: list[Line]) -> list[dict]:
    """Polylines back in answer form."""
    return [{"points": [{"x": x, "y": y} for x, y in line]} for line in lines]


def _midpoint(portal: dict) -> Point:
    """A portal's midpoint."""
    return (portal["x1"] + portal["x2"]) / 2, (portal["y1"] + portal["y2"]) / 2


Tagged = tuple[Line, object]  # a polyline and the side it came from (a chunk, "in", "out")
SeamLine = tuple[str, float]  # ("x", at) for a vertical line, ("y", at) for a horizontal one
DOOR_CLEARANCE = 0.15  # squares: two ends stay apart when a portal's middle is this close to
# the gap between them (they are the two sides of a door)


def _across(point: Point, axis: str) -> float:
    """The coordinate of `point` that a seam on `axis` is measured in (x for a vertical one)."""
    return point[0] if axis == "x" else point[1]


def _along_coord(point: Point, axis: str) -> float:
    """The coordinate of `point` along a seam on `axis` (y for a vertical one)."""
    return point[1] if axis == "x" else point[0]


def _along_seam(line: Line, axis: str, at: float, tolerance: float) -> bool:
    """Whether every point of a polyline lies within `tolerance` of the seam line."""
    return all(abs(_across(p, axis) - at) <= tolerance for p in line)


def _dedupe_along_seams(
    pieces: list[Tagged], seam_lines: list[SeamLine], tolerance: float
) -> tuple[list[Tagged], int]:
    """Keep once a wall that both neighbours drew along a seam.

    Two pieces from different sides that both lie within `tolerance` of the same seam line,
    and whose extents along it overlap by at least 80% of the shorter one, are the same wall:
    the one with the shorter extent is dropped. Returns the pieces and how many were dropped.
    """
    alive = [True] * len(pieces)
    dropped = 0
    for axis, at in seam_lines:
        near = [i for i, (line, _) in enumerate(pieces) if _along_seam(line, axis, at, tolerance)]
        spans = {}
        for i in near:
            coords = [_along_coord(p, axis) for p in pieces[i][0]]
            spans[i] = (min(coords), max(coords))
        for a_pos, i in enumerate(near):
            for j in near[a_pos + 1 :]:
                if not (alive[i] and alive[j]) or pieces[i][1] == pieces[j][1]:
                    continue
                (lo_i, hi_i), (lo_j, hi_j) = spans[i], spans[j]
                overlap = min(hi_i, hi_j) - max(lo_i, lo_j)
                shorter = min(hi_i - lo_i, hi_j - lo_j)
                if shorter > EPS and overlap >= 0.8 * shorter:
                    loser = j if (hi_j - lo_j) <= (hi_i - lo_i) else i
                    alive[loser] = False
                    dropped += 1
    return [piece for piece, keep in zip(pieces, alive, strict=True) if keep], dropped


def _blocked_by_door(a: Point, b: Point, portals: list[dict]) -> bool:
    """Whether a portal sits in the gap between two wall ends (the two sides of a door)."""
    return any(_distance_to_segment(_midpoint(p), a, b) <= DOOR_CLEARANCE for p in portals)


def _pair_and_join(
    pieces: list[Tagged], seam_lines: list[SeamLine], tolerance: float, portals: list[dict]
) -> tuple[list[Line], int, int]:
    """Join wall ends across seams, one to one.

    Candidates are pairs of ends from different sides, both within `tolerance` of the same
    seam line and of each other, on opposite sides of that line (or on it), with no portal
    between them, so a wall running just beside a seam is never pulled onto it. The closest
    pairs are taken first and each end is used once (no chains). Both ends of a pair move to
    the point on the seam between them, and the two polylines become one. Returns the lines,
    the number of ends moved and the number of joins.
    """
    lines = [list(line) for line, _ in pieces]
    tags = [tag for _, tag in pieces]
    candidates = []
    for axis, at in seam_lines:
        near = [
            (i, k)
            for i, line in enumerate(lines)
            for k in (0, -1)
            if abs(_across(line[k], axis) - at) <= tolerance
        ]
        for n_a, (i, ki) in enumerate(near):
            for j, kj in near[n_a + 1 :]:
                if i == j or tags[i] == tags[j]:
                    continue
                pa, pb = lines[i][ki], lines[j][kj]
                d = math.dist(pa, pb)
                straddles = (_across(pa, axis) - at) * (_across(pb, axis) - at) <= EPS
                if d <= tolerance and straddles and not _blocked_by_door(pa, pb, portals):
                    candidates.append((d, i, ki, j, kj, axis, at))
    used: set[tuple[int, int]] = set()
    meetings = []
    for _, i, ki, j, kj, axis, at in sorted(candidates):
        if (i, ki) in used or (j, kj) in used:
            continue
        used |= {(i, ki), (j, kj)}
        along = (_along_coord(lines[i][ki], axis) + _along_coord(lines[j][kj], axis)) / 2
        point = (at, along) if axis == "x" else (along, at)
        point = (round(point[0], 9), round(point[1], 9))
        lines[i][ki] = lines[j][kj] = point
        meetings.append(point)

    joins = 0
    for point in meetings:
        found = [
            (i, k) for i, line in enumerate(lines) if line for k in (0, -1) if line[k] == point
        ]
        if len(found) != 2 or found[0][0] == found[1][0]:
            continue
        (i, ki), (j, kj) = found
        a = lines[i] if ki == -1 else lines[i][::-1]  # a ends at the point
        b = lines[j] if kj == 0 else lines[j][::-1]  # b starts at it
        lines[i] = a + b[1:]
        lines[j] = []
        joins += 1
    return [line for line in lines if line], 2 * len(meetings), joins


def _seam_lines(layout: list[Chunk]) -> tuple[list[float], list[float]]:
    """The x of every vertical seam and the y of every horizontal one."""
    w, h = _extent(layout)
    xs = sorted({c.core[2] for c in layout if c.core[2] < w - EPS})
    ys = sorted({c.core[3] for c in layout if c.core[3] < h - EPS})
    return xs, ys


def merge_answers(
    layout: list[Chunk],
    answers: dict[int, dict],
    map_size: tuple[int, int],
    join_tolerance: float,
    min_piece: float,
) -> tuple[dict, MergeReport]:
    """Merge the chunk agents' answers into one answer for the whole map, by fixed rules.

    `answers` maps chunk index to that agent's answer (chunks with none are left out). Each
    chunk keeps the parts of its walls inside its core and the portals and lights its core
    owns; then a wall drawn along a seam by both neighbours is kept once, and wall ends near a
    seam are paired across it and joined (module docstring). The result has `walls`,
    `portals` and `lights`, and no `arcs`.
    """
    report = MergeReport()
    n = len(layout)
    report.portals_kept, report.portals_dropped = [0] * n, [0] * n
    report.lights_kept, report.lights_dropped = [0] * n, [0] * n
    pieces: list[Tagged] = []
    portals: list[dict] = []
    lights: list[dict] = []
    for chunk in layout:
        answer = answers.get(chunk.index)
        if answer is None:
            continue
        lines = _lines(answer)
        report.walls_in += len(lines)
        for line in lines:
            for piece in clip_polyline(line, chunk.core):
                if _length(piece) < min_piece:
                    report.pieces_dropped += 1
                else:
                    pieces.append((piece, chunk.index))
        for portal in answer.get("portals", []):
            if owner(*_midpoint(portal), layout) == chunk.index:
                portals.append(portal)
                report.portals_kept[chunk.index] += 1
            else:
                report.portals_dropped[chunk.index] += 1
        for light in answer.get("lights", []):
            if owner(light["x"], light["y"], layout) == chunk.index:
                lights.append(light)
                report.lights_kept[chunk.index] += 1
            else:
                report.lights_dropped[chunk.index] += 1
    xs, ys = _seam_lines(layout)
    seam_lines = [("x", x) for x in xs] + [("y", y) for y in ys]
    pieces, report.walls_deduped = _dedupe_along_seams(pieces, seam_lines, join_tolerance)
    joined, report.ends_snapped, report.joins = _pair_and_join(
        pieces, seam_lines, join_tolerance, portals
    )
    report.walls_out = len(joined)
    return {"walls": _walls(joined), "portals": portals, "lights": lights}, report


# --- Seams and the review --------------------------------------------------------------------


def seams(layout: list[Chunk], map_size: tuple[int, int], strip_squares: float) -> list[Seam]:
    """Every seam of a layout with its strip, `strip_squares` either side, clipped to the map.

    (nx - 1) + (ny - 1) seams, vertical ones first; none for a one-chunk layout.
    """
    w, h = map_size
    xs, ys = _seam_lines(layout)
    out = [
        Seam("x", x, (max(0.0, x - strip_squares), 0.0, min(w, x + strip_squares), h)) for x in xs
    ]
    out += [
        Seam("y", y, (0.0, max(0.0, y - strip_squares), w, min(h, y + strip_squares))) for y in ys
    ]
    return out


def _in_any(x: float, y: float, boxes: list[Box]) -> bool:
    """Whether a point lies in any of `boxes` (edges included)."""
    return any(b[0] <= x <= b[2] and b[1] <= y <= b[3] for b in boxes)


def apply_review(
    merged: dict,
    submission: dict,
    strips: list[Box],
    map_size: tuple[int, int],
    join_tolerance: float,
    min_piece: float,
) -> tuple[dict, dict, dict]:
    """Replace the merged answer's content inside the strips with the review's submission.

    Nothing outside the strips changes: merged walls keep their parts outside the strips'
    union, merged portals and lights outside are kept; the submission contributes only its
    parts inside the strips. Wall ends near the strip edges are then paired across them (a
    merged end with a submitted one, closest first, never through a door) and joined, as in
    the merge. Returns (final answer, removed counts, added counts), each count dict with
    `walls`, `portals` and `lights`.
    """
    w, h = map_size
    removed = {"walls": 0, "portals": 0, "lights": 0}
    added = {"walls": 0, "portals": 0, "lights": 0}
    lines: list[Tagged] = []
    for line in _lines(merged):
        outside = [p for p in clip_polyline_outside(line, strips) if _length(p) >= min_piece]
        if outside != [line]:
            removed["walls"] += 1
        lines += [(p, "out") for p in outside]
    for line in _lines(submission):
        inside = [p for p in clip_polyline_inside(line, strips) if _length(p) >= min_piece]
        added["walls"] += len(inside)
        lines += [(p, "in") for p in inside]

    def split(items: list[dict], where) -> tuple[list[dict], list[dict]]:
        """Items outside and inside the strips."""
        out, ins = [], []
        for item in items:
            (ins if _in_any(*where(item), strips) else out).append(item)
        return out, ins

    portals, gone = split(merged.get("portals", []), _midpoint)
    removed["portals"] = len(gone)
    _, new = split(submission.get("portals", []), _midpoint)
    added["portals"] = len(new)
    portals += new
    lights, gone = split(merged.get("lights", []), lambda li: (li["x"], li["y"]))
    removed["lights"] = len(gone)
    _, new = split(submission.get("lights", []), lambda li: (li["x"], li["y"]))
    added["lights"] = len(new)
    lights += new

    xs = sorted({x for s in strips for x in (s[0], s[2]) if EPS < x < w - EPS})
    ys = sorted({y for s in strips for y in (s[1], s[3]) if EPS < y < h - EPS})
    edges = [("x", x) for x in xs] + [("y", y) for y in ys]
    joined, _, _ = _pair_and_join(lines, edges, join_tolerance, portals)
    return {"walls": _walls(joined), "portals": portals, "lights": lights}, removed, added


def _distance_to_segment(p: Point, a: Point, b: Point) -> float:
    """The distance from point p to segment a-b."""
    dx, dy = b[0] - a[0], b[1] - a[1]
    if dx == dy == 0:
        return math.dist(p, a)
    t = max(0.0, min(1.0, ((p[0] - a[0]) * dx + (p[1] - a[1]) * dy) / (dx * dx + dy * dy)))
    return math.dist(p, (a[0] + t * dx, a[1] + t * dy))


def _close_pairs(points: list[Point], same: float) -> int:
    """How many pairs of points are within `same` squares of each other."""
    return sum(
        1
        for i in range(len(points))
        for j in range(i + 1, len(points))
        if math.dist(points[i], points[j]) <= same
    )


def seam_checks(
    answer: dict, seam_list: list[Seam], gap: float = 0.1, same: float = 0.5
) -> dict[str, int]:
    """Count what spec SC-003 forbids in an answer: wall ends left hanging on a seam, and
    portals or lights reported twice.

    `seam_gap_ends`: wall ends on a seam with no point of another wall within `gap` squares.
    `duplicate_portals` / `duplicate_lights`: pairs of midpoints or positions within `same`.
    """
    xs = [s.at for s in seam_list if s.axis == "x"]
    ys = [s.at for s in seam_list if s.axis == "y"]

    def on_seam(point: Point) -> bool:
        """Whether a wall end lies on one of the seams."""
        return any(abs(point[0] - x) < EPS for x in xs) or any(abs(point[1] - y) < EPS for y in ys)

    lines = _lines(answer)
    gaps = 0
    for i, line in enumerate(lines):
        for end in (line[0], line[-1]):
            if not on_seam(end):
                continue
            near = any(
                _distance_to_segment(end, a, b) <= gap
                for j, other in enumerate(lines)
                if j != i
                for a, b in pairwise(other)
            )
            gaps += not near
    return {
        "seam_gap_ends": gaps,
        "duplicate_portals": _close_pairs([_midpoint(p) for p in answer.get("portals", [])], same),
        "duplicate_lights": _close_pairs(
            [(li["x"], li["y"]) for li in answer.get("lights", [])], same
        ),
    }
