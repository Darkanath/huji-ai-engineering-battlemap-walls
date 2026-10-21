"""Place furniture, light sources and unlit fixtures on a layout.

Everything here is geometry in grid squares; `render` draws it. Placement works on cells:
a cell holds at most one item, and the cells on both sides of every opening stay free so no
doorway or gap is blocked. Wall-mounted items (torches, fireplaces, shelves, beds, counters)
stand on a wall edge and face into the room through the edge's normal.

Lit light sources become .dd2vtt lights with the `range` of their tier (data/rasterize.py,
LIGHT_TIERS); unlit fixtures are drawn the same way without a flame and get no light.
"""

from dataclasses import dataclass

import numpy as np

from data.rasterize import LIGHT_TIERS
from data.synth.layout import Edge, Layout

Cell = tuple[int, int]

# Light kinds per tier, and which of them hang on a wall.
LIGHT_KINDS = {
    "small": ["torch", "torch", "candle"],
    "medium": ["brazier", "campfire", "lantern", "fireplace"],
    "large": ["bonfire"],
}
WALL_KINDS = {"torch", "fireplace"}
UNLIT_KINDS = ["torch", "brazier", "campfire", "fireplace", "lantern"]
TORCH_OFFSET = 0.22  # squares from the wall line to a torch's flame
FIREPLACE_OFFSET = 0.35  # squares from the wall line to the fire in a fireplace
FURNITURE_OFFSET = 0.12  # squares between the wall line and furniture against it


@dataclass
class Item:
    """One placed object: center (x, y) and size (w, h) in squares, plus how to draw it.

    `normal` is the direction from the wall into the room for wall-mounted items, else None.
    `lit` and `tier` are set for light sources (lit or unlit fixtures); `has_candle` marks a
    table that already holds a candle.
    """

    kind: str
    x: float
    y: float
    w: float
    h: float
    normal: tuple[int, int] | None = None
    lit: bool = False
    tier: str | None = None
    has_candle: bool = False


@dataclass
class WallSlot:
    """The room side of one wall edge: the cell in front of it and the normal into that cell."""

    edge: Edge
    cell: Cell
    normal: tuple[int, int]

    def point(self, offset: float) -> tuple[float, float]:
        """A point `offset` squares from the middle of the edge, into the room."""
        orient, x, y = self.edge
        mx, my = (x + 0.5, y) if orient == "h" else (x, y + 0.5)
        return mx + self.normal[0] * offset, my + self.normal[1] * offset


class Dresser:
    """Places items on one layout while tracking which cells and wall edges are taken."""

    def __init__(self, rng: np.random.Generator, layout: Layout):
        """Index the layout's free cells and wall slots."""
        self.rng = rng
        self.layout = layout
        self.items: list[Item] = []
        self.taken: set[Cell] = set()
        self.used_edges: set[Edge] = set()
        self.reserved = self._opening_cells()
        self.slots = self._wall_slots()
        wall_cells = {s.cell for s in self.slots}
        height, width = layout.regions.shape
        self.inside = [
            (x, y) for y in range(height) for x in range(width) if layout.regions[y, x] > 0
        ]
        self.open_floor = [c for c in self.inside if c not in wall_cells]
        self.outside = [
            (x, y)
            for y in range(1, height - 1)
            for x in range(1, width - 1)
            if layout.regions[y, x] == 0 and (x, y) not in wall_cells
        ]

    def _opening_cells(self) -> set[Cell]:
        """Cells on both sides of every opening (kept free)."""
        cells = set()
        for opening in self.layout.openings:
            for orient, x, y in opening.edges():
                cells.update([(x, y - 1), (x, y)] if orient == "h" else [(x - 1, y), (x, y)])
        return cells

    def _wall_slots(self) -> list[WallSlot]:
        """Both inner sides of every wall edge (sides facing a room or corridor, not outside)."""
        regions = self.layout.regions
        slots = []
        for edge in sorted(self.layout.wall_edges):
            orient, x, y = edge
            sides = (
                [((x, y), (0, 1)), ((x, y - 1), (0, -1))]
                if orient == "h"
                else [((x, y), (1, 0)), ((x - 1, y), (-1, 0))]
            )
            for (cx, cy), normal in sides:
                if 0 <= cy < regions.shape[0] and 0 <= cx < regions.shape[1]:
                    if regions[cy, cx] > 0:
                        slots.append(WallSlot(edge, (cx, cy), normal))
        return slots

    def _free(self, cell: Cell) -> bool:
        """True if nothing stands on the cell and it doesn't touch an opening."""
        return cell not in self.taken and cell not in self.reserved

    def _pick(self, options: list):
        """A random element of `options`, or None if empty."""
        return options[int(self.rng.integers(len(options)))] if options else None

    def _free_slot(self) -> WallSlot | None:
        """A wall slot whose cell is free and whose edge (and neighbours) are unused."""
        options = [
            s
            for s in self.slots
            if self._free(s.cell) and not (_neighbours(s.edge) & self.used_edges)
        ]
        return self._pick(options)

    def _wall_run(self, length: int) -> list[WallSlot] | None:
        """`length` slots in a row along one wall, facing the same way, all free."""
        by_key = {(s.edge, s.normal): s for s in self.slots}
        starts = []
        for s in self.slots:
            run = [s]
            for _ in range(length - 1):
                nxt = by_key.get((_next_edge(run[-1].edge), s.normal))
                if nxt is None:
                    break
                run.append(nxt)
            if len(run) == length and all(
                self._free(r.cell) and r.edge not in self.used_edges for r in run
            ):
                starts.append(run)
        return self._pick(starts)

    def _take_slots(self, run: list[WallSlot]) -> None:
        """Mark the cells and edges of a wall run as taken."""
        for s in run:
            self.taken.add(s.cell)
            self.used_edges.add(s.edge)

    def wall_item(self, kind: str, depth: float, length: int = 1, **light) -> Item | None:
        """An item against a wall: `length` squares along it, `depth` squares into the room."""
        run = self._wall_run(length)
        if run is None:
            return None
        self._take_slots(run)
        (ax, ay), (bx, by) = run[0].point(0), run[-1].point(0)
        nx, ny = run[0].normal
        offset = FURNITURE_OFFSET + depth / 2
        cx, cy = (ax + bx) / 2 + nx * offset, (ay + by) / 2 + ny * offset
        along = length - 0.2
        w, h = (along, depth) if ny else (depth, along)
        item = Item(kind, cx, cy, w, h, normal=(nx, ny), **light)
        self.items.append(item)
        return item

    def wall_light(self, kind: str, lit: bool, tier: str) -> Item | None:
        """A torch or fireplace on a wall; its position is where the flame is."""
        slot = self._free_slot()
        if slot is None:
            return None
        self._take_slots([slot])
        offset = TORCH_OFFSET if kind == "torch" else FIREPLACE_OFFSET
        x, y = slot.point(offset)
        size = 0.3 if kind == "torch" else 0.9
        item = Item(kind, x, y, size, size, normal=slot.normal, lit=lit, tier=tier)
        self.items.append(item)
        return item

    def floor_item(self, kind: str, size: float, cells: int = 1, **extra) -> Item | None:
        """An item on open floor: one free cell, or a free `cells` x `cells` block."""
        options = []
        pool = self.open_floor + (self.outside if kind in {"campfire", "bonfire"} else [])
        pool_set = set(pool)
        for x, y in pool:
            block = [(x + i, y + j) for i in range(cells) for j in range(cells)]
            if all(self._free(c) and c in pool_set for c in block):
                options.append(block)
        block = self._pick(options)
        if block is None:
            return None
        self.taken.update(block)
        jitter = self.rng.uniform(-0.12, 0.12, size=2) if cells == 1 else (0.0, 0.0)
        cx = block[0][0] + cells / 2 + float(jitter[0])
        cy = block[0][1] + cells / 2 + float(jitter[1])
        item = Item(kind, cx, cy, size, size, **extra)
        self.items.append(item)
        return item


def _next_edge(edge: Edge) -> Edge:
    """The next edge along the same grid line."""
    orient, x, y = edge
    return (orient, x + 1, y) if orient == "h" else (orient, x, y + 1)


def _neighbours(edge: Edge) -> set[Edge]:
    """The edge and the edges next to it on the same line."""
    orient, x, y = edge
    if orient == "h":
        return {("h", x - 1, y), edge, ("h", x + 1, y)}
    return {("v", x, y - 1), edge, ("v", x, y + 1)}


def _place_furniture(d: Dresser, rng: np.random.Generator, cfg: dict) -> None:
    """Rugs, then furniture against walls and on the floor, scaled to the inside area."""
    lo, hi = cfg["per_room"]
    rooms = sum(1 for kind in d.layout.kinds.values() if kind == "room")
    count = int(rng.integers(lo * rooms, hi * rooms + 1))
    for _ in range(int(rng.integers(0, rooms + 1))):  # rugs lie under everything
        cell = d._pick([c for c in d.open_floor if d._free(c)])
        if cell:
            w, h = rng.uniform(1.2, 2.6, size=2)
            d.items.append(Item("rug", cell[0] + 0.5, cell[1] + 0.5, float(w), float(h)))
    wall_kinds = [("shelf", 0.4), ("counter", 0.55), ("bed", 0.9)]
    floor_kinds = [("table", 0.8), ("barrel", 0.6), ("crate", 0.7), ("pillar", 0.6)]
    for _ in range(count):
        if rng.random() < cfg["against_wall_share"]:
            kind, depth = wall_kinds[int(rng.integers(len(wall_kinds)))]
            length = 2 if kind == "bed" else int(rng.integers(2, 5))
            d.wall_item(kind, depth, length)
        else:
            kind, size = floor_kinds[int(rng.integers(len(floor_kinds)))]
            d.floor_item(kind, size)


def _place_light(d: Dresser, kind: str, lit: bool, tier: str) -> Item | None:
    """One light source or unlit fixture of `kind`; candles go on a table when there is one."""
    if kind in WALL_KINDS:
        return d.wall_light(kind, lit, tier)
    if kind == "candle":
        tables = [i for i in d.items if i.kind == "table" and not i.has_candle]
        table = d._pick(tables)
        if table is not None:
            table.has_candle = True
            dx, dy = d.rng.uniform(-0.2, 0.2, size=2)
            item = Item("candle", table.x + dx, table.y + dy, 0.2, 0.2, lit=lit, tier=tier)
            d.items.append(item)
            return item
    sizes = {"candle": 0.25, "lantern": 0.4, "brazier": 0.7, "campfire": 0.8, "bonfire": 1.5}
    cells = 2 if kind == "bonfire" else 1
    return d.floor_item(kind, sizes[kind], cells, lit=lit, tier=tier)


def dress(rng: np.random.Generator, layout: Layout, cfg: dict) -> tuple[list[Item], list[dict]]:
    """Place furniture, lit light sources and unlit fixtures; return items and .dd2vtt lights."""
    d = Dresser(rng, layout)
    _place_furniture(d, rng, cfg["furniture"])

    lcfg = cfg["lights"]
    tiers, weights = zip(*lcfg["tier_weights"].items(), strict=True)
    p = np.array(weights) / sum(weights)
    lo, hi = lcfg["lit"]
    for _ in range(int(rng.integers(lo, hi + 1))):
        tier = str(rng.choice(tiers, p=p))
        kinds = LIGHT_KINDS[tier]
        for kind in [kinds[int(rng.integers(len(kinds)))], *kinds, *LIGHT_KINDS["small"]]:
            fallback = tier if kind in kinds else "small"
            if _place_light(d, kind, True, fallback):
                break
    lo, hi = lcfg["unlit"]
    for _ in range(int(rng.integers(lo, hi + 1))):
        kind = UNLIT_KINDS[int(rng.integers(len(UNLIT_KINDS)))]
        tier = next(t for t, ks in LIGHT_KINDS.items() if kind in ks)
        _place_light(d, kind, False, tier)

    lights = [
        {
            "position": {"x": round(i.x, 4), "y": round(i.y, 4)},
            "range": LIGHT_TIERS[i.tier]["range"],
            "intensity": 1.0,
            "color": "ffeccd8b",
            "shadows": True,
        }
        for i in d.items
        if i.lit
    ]
    return d.items, lights
