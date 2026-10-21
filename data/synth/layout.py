"""Room-and-corridor layouts on the square grid, with walls and openings on the grid lines.

Coordinates are in grid squares. Cell (x, y) is the square from (x, y) to (x + 1, y + 1).
Every cell belongs to a region: 0 is outside, every room and every corridor has its own id.
A wall stands on every grid edge between two different regions, except where an opening is:

- door: a portal (closed) in the wall, 1 or 2 squares wide (2 is a double door);
- window: a portal (open) in an outer wall, 1 square wide;
- gap: no wall and no portal, 1 to 3 squares wide (a doorless opening).

Edges are named ("h", x, y) for the horizontal edge from vertex (x, y) to (x + 1, y), which
separates cell (x, y - 1) from cell (x, y), and ("v", x, y) for the vertical edge from (x, y) to
(x, y + 1), which separates cell (x - 1, y) from cell (x, y).
"""

from collections import defaultdict
from dataclasses import dataclass, field

import numpy as np

Edge = tuple[str, int, int]
Point = tuple[int, int]


@dataclass
class Opening:
    """A door, window or gap covering `length` consecutive edges from edge (orient, x, y)."""

    kind: str  # "door", "window" or "gap"
    orient: str  # "h" or "v"
    x: int
    y: int
    length: int

    def edges(self) -> list[Edge]:
        """The grid edges this opening covers."""
        if self.orient == "h":
            return [("h", self.x + i, self.y) for i in range(self.length)]
        return [("v", self.x, self.y + i) for i in range(self.length)]

    def endpoints(self) -> tuple[tuple[float, float], tuple[float, float]]:
        """The opening's two ends, in grid squares."""
        if self.orient == "h":
            return (self.x, self.y), (self.x + self.length, self.y)
        return (self.x, self.y), (self.x, self.y + self.length)


@dataclass
class Layout:
    """A generated layout: regions per cell, wall polylines and openings."""

    width: int
    height: int
    regions: np.ndarray  # (height, width) int, 0 = outside
    kinds: dict[int, str]  # region id -> "room" or "corridor"
    style: str  # "building" or "dungeon"
    walls: list[list[Point]] = field(default_factory=list)
    wall_edges: set[Edge] = field(default_factory=set)
    openings: list[Opening] = field(default_factory=list)


@dataclass
class _Node:
    """A node of the binary space partition: a rectangle (x, y, w, h) and its children."""

    rect: tuple[int, int, int, int]
    children: list["_Node"] = field(default_factory=list)

    def leaves(self) -> list["_Node"]:
        """All leaf nodes under this one, left to right."""
        if not self.children:
            return [self]
        return [leaf for child in self.children for leaf in child.leaves()]


def _split(rng: np.random.Generator, node: _Node, min_leaf: int, max_leaf: int) -> None:
    """Recursively split `node` until its leaves are between min_leaf and max_leaf squares."""
    x, y, w, h = node.rect
    can_w, can_h = w >= 2 * min_leaf, h >= 2 * min_leaf
    must = w > max_leaf or h > max_leaf
    if not (can_w or can_h) or (not must and rng.random() < 0.35):
        return
    vertical = can_w and (not can_h or w > h or (w == h and rng.random() < 0.5))
    if vertical:
        cut = int(rng.integers(min_leaf, w - min_leaf + 1))
        node.children = [_Node((x, y, cut, h)), _Node((x + cut, y, w - cut, h))]
    else:
        cut = int(rng.integers(min_leaf, h - min_leaf + 1))
        node.children = [_Node((x, y, w, cut)), _Node((x, y + cut, w, h - cut))]
    for child in node.children:
        _split(rng, child, min_leaf, max_leaf)


def _shrink(rng: np.random.Generator, rect: tuple[int, int, int, int]) -> tuple[int, ...]:
    """A room inside a BSP leaf: the leaf with 0-2 squares cut from each side, at least 3x3."""
    x, y, w, h = rect
    cuts = rng.integers(0, 3, size=4)
    left, top = int(cuts[0]), int(cuts[1])
    right, bottom = int(cuts[2]), int(cuts[3])
    while w - left - right < 3:
        left, right = max(0, left - 1), max(0, right - 1)
    while h - top - bottom < 3:
        top, bottom = max(0, top - 1), max(0, bottom - 1)
    return x + left, y + top, w - left - right, h - top - bottom


def _carve_corridor(
    rng: np.random.Generator, regions: np.ndarray, a: tuple, b: tuple, width: int
) -> None:
    """Carve an L-shaped corridor between room rects a and b into outside cells (marked -1)."""
    ax, ay = a[0] + a[2] // 2, a[1] + a[3] // 2
    bx, by = b[0] + b[2] // 2, b[1] + b[3] // 2
    corner = (bx, ay) if rng.random() < 0.5 else (ax, by)
    for (x0, y0), (x1, y1) in [((ax, ay), corner), (corner, (bx, by))]:
        xs = range(min(x0, x1), max(x0, x1) + width)
        ys = range(min(y0, y1), max(y0, y1) + width)
        for y in ys:
            for x in xs:
                if 0 < x < regions.shape[1] - 1 and 0 < y < regions.shape[0] - 1:
                    if regions[y, x] == 0:
                        regions[y, x] = -1


def _label_corridors(regions: np.ndarray, first_id: int) -> list[int]:
    """Give each connected group of corridor cells (-1) its own region id; return the ids."""
    ids, next_id = [], first_id
    height, width = regions.shape
    for sy in range(height):
        for sx in range(width):
            if regions[sy, sx] != -1:
                continue
            stack = [(sx, sy)]
            regions[sy, sx] = next_id
            while stack:
                x, y = stack.pop()
                for nx, ny in ((x + 1, y), (x - 1, y), (x, y + 1), (x, y - 1)):
                    if 0 <= nx < width and 0 <= ny < height and regions[ny, nx] == -1:
                        regions[ny, nx] = next_id
                        stack.append((nx, ny))
            ids.append(next_id)
            next_id += 1
    return ids


def boundary_edges(regions: np.ndarray) -> dict[tuple[int, int], list[Edge]]:
    """Every edge between two different regions, grouped by the (sorted) pair of region ids.

    Edges to the outside are grouped under (0, region).
    """
    pairs: dict[tuple[int, int], list[Edge]] = defaultdict(list)
    height, width = regions.shape
    for y in range(1, height):
        for x in range(width):
            a, b = int(regions[y - 1, x]), int(regions[y, x])
            if a != b:
                pairs[(min(a, b), max(a, b))].append(("h", x, y))
    for x in range(1, width):
        for y in range(height):
            a, b = int(regions[y, x - 1]), int(regions[y, x])
            if a != b:
                pairs[(min(a, b), max(a, b))].append(("v", x, y))
    return pairs


def straight_runs(edges: list[Edge]) -> list[list[Edge]]:
    """Group edges into runs of consecutive edges on one grid line, in a fixed order."""
    lines: dict[tuple[str, int], list[int]] = defaultdict(list)
    for orient, x, y in edges:
        line, pos = (y, x) if orient == "h" else (x, y)
        lines[(orient, line)].append(pos)
    runs = []
    for (orient, line), positions in sorted(lines.items()):
        positions.sort()
        start = prev = positions[0]
        for pos in positions[1:] + [None]:
            if pos is not None and pos == prev + 1:
                prev = pos
                continue
            span = range(start, prev + 1)
            runs.append([(orient, p, line) if orient == "h" else (orient, line, p) for p in span])
            if pos is not None:
                start = prev = pos
    return runs


def _blocked(edge: Edge) -> list[Edge]:
    """The edge and its two neighbours on the same line (openings keep one edge of wall apart)."""
    orient, x, y = edge
    if orient == "h":
        return [("h", x - 1, y), edge, ("h", x + 1, y)]
    return [("v", x, y - 1), edge, ("v", x, y + 1)]


def _place_opening(
    rng: np.random.Generator,
    edges: list[Edge],
    kind: str,
    length: int,
    used: set[Edge],
    margin: int = 0,
) -> Opening | None:
    """Place an opening of `length` edges on one run of `edges`, away from used edges.

    `margin` keeps that many wall edges at each end of the run (windows keep 1, so they never
    sit in a corner). Returns None if no run has room.
    """
    candidates = []
    for run in straight_runs(edges):
        for start in range(margin, len(run) - length - margin + 1):
            span = run[start : start + length]
            if not any(e in used for edge in span for e in _blocked(edge)):
                candidates.append(span)
    if not candidates:
        return None
    span = candidates[int(rng.integers(len(candidates)))]
    orient, x, y = span[0]
    used.update(span)
    return Opening(kind, orient, x, y, len(span))


def _connect(
    rng: np.random.Generator, edges: list[Edge], cfg: dict, used: set[Edge]
) -> Opening | None:
    """A door (single or double) or a doorless gap on the boundary between two regions."""
    if rng.random() < cfg["gap_probability"]:
        lo, hi = cfg["gap_width"]
        for length in range(int(rng.integers(lo, hi + 1)), 0, -1):
            opening = _place_opening(rng, edges, "gap", length, used)
            if opening:
                return opening
    double = rng.random() < cfg["double_door_probability"]
    for length in [2, 1] if double else [1]:
        opening = _place_opening(rng, edges, "door", length, used)
        if opening:
            return opening
    return None


def _find(parent: dict[int, int], a: int) -> int:
    """Union-find root of `a`, with path halving."""
    while parent[a] != a:
        parent[a] = parent[parent[a]]
        a = parent[a]
    return a


def _make_openings(
    rng: np.random.Generator, layout: Layout, pairs: dict, cfg: dict
) -> list[Opening]:
    """Doors and gaps that connect every region, entrances from outside, and windows."""
    used: set[Edge] = set()
    openings: list[Opening] = []
    inner = [p for p in sorted(pairs) if p[0] != 0]
    order = rng.permutation(len(inner))
    parent = {rid: rid for rid in layout.kinds}
    for i in order:
        a, b = inner[i]
        joined = _find(parent, a) != _find(parent, b)
        if joined or rng.random() < cfg["extra_opening_probability"]:
            opening = _connect(rng, pairs[(a, b)], cfg, used)
            if opening:
                openings.append(opening)
                parent[_find(parent, a)] = _find(parent, b)

    outer = [p for p in sorted(pairs) if p[0] == 0]
    if outer:
        lo, hi = cfg["entrances"]
        for _ in range(int(rng.integers(lo, hi + 1))):
            pair = outer[int(rng.integers(len(outer)))]
            opening = _connect(rng, pairs[pair], cfg, used)
            if opening:
                openings.append(opening)
        window_p = cfg["window_probability"][layout.style]
        for pair in outer:
            for run in straight_runs(pairs[pair]):
                if len(run) >= 3 and rng.random() < window_p:
                    opening = _place_opening(rng, run, "window", 1, used, margin=1)
                    if opening:
                        openings.append(opening)

    if not any(o.kind == "gap" for o in openings):
        doors = [o for o in openings if o.kind == "door"]
        if doors:
            doors[int(rng.integers(len(doors)))].kind = "gap"
    return openings


def trace_polylines(edges: set[Edge]) -> list[list[Point]]:
    """Join wall edges into polylines through corners; straight points are dropped.

    A polyline ends where three or four walls meet, at a free end, or where it closes a loop.
    """
    adj: dict[Point, list[Point]] = defaultdict(list)
    for orient, x, y in sorted(edges):
        a, b = ((x, y), (x + 1, y)) if orient == "h" else ((x, y), (x, y + 1))
        adj[a].append(b)
        adj[b].append(a)
    done: set[frozenset] = set()

    def walk(start: Point, nxt: Point) -> list[Point]:
        """Follow edges from `start` through degree-2 vertices until a stop."""
        line = [start, nxt]
        done.add(frozenset((start, nxt)))
        cur = nxt
        while len(adj[cur]) == 2 and cur != start:
            step = next((n for n in adj[cur] if frozenset((cur, n)) not in done), None)
            if step is None:
                break
            done.add(frozenset((cur, step)))
            line.append(step)
            cur = step
        return line

    lines = []
    for v in sorted(adj):
        if len(adj[v]) != 2:
            for n in adj[v]:
                if frozenset((v, n)) not in done:
                    lines.append(walk(v, n))
    for v in sorted(adj):  # closed loops: every vertex has degree 2
        for n in adj[v]:
            if frozenset((v, n)) not in done:
                lines.append(walk(v, n))
    return [_drop_straight(line) for line in lines]


def _drop_straight(line: list[Point]) -> list[Point]:
    """Remove points in the middle of a straight stretch."""
    out = [line[0]]
    for i in range(1, len(line) - 1):
        (ax, ay), (bx, by), (cx, cy) = out[-1], line[i], line[i + 1]
        if (bx - ax) * (cy - by) != (by - ay) * (cx - bx):
            out.append(line[i])
    out.append(line[-1])
    return out


def generate_layout(rng: np.random.Generator, width: int, height: int, cfg: dict) -> Layout:
    """A random layout of `width` x `height` squares, building or dungeon style.

    Building style: the rooms tile a rectangle and share their walls. Dungeon style: smaller
    rooms joined by corridors 1 or 2 squares wide. Every room and corridor is reachable.
    """
    style = "building" if rng.random() < cfg["building_probability"] else "dungeon"
    regions = np.zeros((height, width), dtype=np.int32)
    margin = int(rng.integers(1, 4)) if style == "building" else 1
    root = _Node((margin, margin, width - 2 * margin, height - 2 * margin))
    _split(rng, root, cfg["min_leaf"], cfg["max_leaf"])

    rooms = []
    for i, leaf in enumerate(root.leaves(), start=1):
        rect = leaf.rect if style == "building" else _shrink(rng, leaf.rect)
        x, y, w, h = rect
        regions[y : y + h, x : x + w] = i
        rooms.append(rect)
        leaf.rect = rect
    kinds = {i: "room" for i in range(1, len(rooms) + 1)}

    if style == "dungeon":
        stack = [root]
        while stack:
            node = stack.pop()
            if node.children:
                left, right = node.children
                a = left.leaves()[int(rng.integers(len(left.leaves())))].rect
                b = right.leaves()[int(rng.integers(len(right.leaves())))].rect
                lo, hi = cfg["corridor_width"]
                _carve_corridor(rng, regions, a, b, int(rng.integers(lo, hi + 1)))
                stack.extend(node.children)
        for rid in _label_corridors(regions, len(rooms) + 1):
            kinds[rid] = "corridor"

    layout = Layout(width, height, regions, kinds, style)
    pairs = boundary_edges(regions)
    layout.openings = _make_openings(rng, layout, pairs, cfg)
    open_edges = {e for o in layout.openings for e in o.edges()}
    layout.wall_edges = {e for edges in pairs.values() for e in edges} - open_edges
    layout.walls = trace_polylines(layout.wall_edges)
    return layout
