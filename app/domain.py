"""The app's domain models and coordinate conversions.

Three coordinate systems, each value in exactly one:

- **Image fractions** (`Point.fx`, `Point.fy` in 0..1 of the image width and height): what the
  app stores, so a map-size change keeps the mask over the same image features.
- **Grid squares**: the model's answer, the export file and label files.
- **Pixels**: drawing the preview.

The model's views are drawn with one pixels-per-square value, `image_width / map_width`, on
both axes, so an answer's `y` is converted with that value, not with the map height
(research.md R2).
"""

from enum import StrEnum
from typing import Literal

from pydantic import BaseModel, Field, field_validator, model_validator

from postprocess.uvtt import arc_points

MIN_SQUARES, MAX_SQUARES = 1, 200


class Point(BaseModel):
    """A position as fractions of the image width and height, origin top-left, y down."""

    fx: float
    fy: float

    @field_validator("fx", "fy")
    @classmethod
    def _clamp(cls, v: float) -> float:
        """Clamp to 0..1: a wall end traced a hair past the border stays on the map."""
        return min(1.0, max(0.0, float(v)))


class Wall(BaseModel):
    """A wall as a polyline; curves arrive here already turned into polylines."""

    points: list[Point] = Field(min_length=2)


class Portal(BaseModel):
    """A door or window, as its two ends. One type for both."""

    a: Point
    b: Point

    @model_validator(mode="after")
    def _distinct(self) -> "Portal":
        """The two ends must differ."""
        if self.a == self.b:
            raise ValueError("a portal's two ends must differ")
        return self


LightTier = Literal["small", "medium", "large"]


class Light(BaseModel):
    """A drawn light source; its range comes from the tier table, never from the image."""

    at: Point
    tier: LightTier


class MapSize(BaseModel):
    """The map's size in grid squares, each side a whole number from 1 to 200."""

    width: int = Field(ge=MIN_SQUARES, le=MAX_SQUARES)
    height: int = Field(ge=MIN_SQUARES, le=MAX_SQUARES)

    def as_tuple(self) -> tuple[int, int]:
        """(width, height), the form `llm.agent` takes."""
        return self.width, self.height


class MapSizeSource(StrEnum):
    """Where the map size on screen came from."""

    default = "default"  # the pre-filled size, untouched
    typed = "typed"  # the user entered it; wins over everything
    detected = "detected"  # the model worked it out during a pass
    not_found = "not_found"  # detection found no grid; the size in the fields was used


class PassKind(StrEnum):
    """Which pass: the fast suggestion or the deeper examination."""

    quick = "quick"
    deep = "deep"


class Usage(BaseModel):
    """Token counts and loop counters for one pass."""

    input_tokens: int = 0
    output_tokens: int = 0
    cache_write_tokens: int = 0
    cache_read_tokens: int = 0
    turns: int = 0
    views: int = 0
    submissions: int = 0


class TraceResult(BaseModel):
    """A successful pass: the mask in image fractions, plus what it cost and how it was made."""

    walls: list[Wall] = []
    portals: list[Portal] = []
    lights: list[Light] = []
    note: str = ""
    kind: PassKind
    model_id: str
    served_by: list[str] = []
    effort: str
    elapsed_s: float
    usage: Usage
    cost_usd: float
    traced_size: MapSize
    size_source: MapSizeSource

    def is_empty(self) -> bool:
        """True when the pass found no walls, portals or lights."""
        return not (self.walls or self.portals or self.lights)

    def counts(self) -> str:
        """ "14 walls, 6 portals, 3 lights", for the status line."""

        def n(items: list, word: str) -> str:
            """ "1 wall", "3 walls"."""
            return f"{len(items)} {word}{'' if len(items) == 1 else 's'}"

        return f"{n(self.walls, 'wall')}, {n(self.portals, 'portal')}, {n(self.lights, 'light')}"


class RawPoint(BaseModel):
    """A point in the model's answer, in grid squares."""

    x: float
    y: float


class RawWall(BaseModel):
    """A polyline in the model's answer."""

    points: list[RawPoint]


class RawArc(BaseModel):
    """A circular wall piece in the model's answer; angles in degrees from east toward south."""

    cx: float
    cy: float
    r: float = Field(gt=0)
    start_deg: float
    end_deg: float


class RawPortal(BaseModel):
    """A portal in the model's answer, as two ends."""

    x1: float
    y1: float
    x2: float
    y2: float


class RawLight(BaseModel):
    """A light in the model's answer."""

    x: float
    y: float
    tier: LightTier


class RawAnswer(BaseModel):
    """The model's `submit_answer` input, in grid squares. Validated at the boundary."""

    walls: list[RawWall] = []
    arcs: list[RawArc] = []
    portals: list[RawPortal] = []
    lights: list[RawLight] = []


def answer_to_fractions(
    raw: RawAnswer, traced_size: MapSize, image_size: tuple[int, int]
) -> tuple[list[Wall], list[Portal], list[Light]]:
    """Convert an answer in grid squares to image fractions.

    `traced_size` is the map size the trace used and `image_size` the image's (width, height)
    in pixels. Arcs become polylines first; walls with fewer than 2 points and portals whose
    ends coincide are dropped.
    """
    image_w, image_h = image_size
    ppg = image_w / traced_size.width

    def frac(x: float, y: float) -> Point:
        """One grid-square point as fractions."""
        return Point(fx=x / traced_size.width, fy=y * ppg / image_h)

    lines = [[(p.x, p.y) for p in w.points] for w in raw.walls]
    for a in raw.arcs:
        lines.append(
            [(p["x"], p["y"]) for p in arc_points(a.cx, a.cy, a.r, a.start_deg, a.end_deg)]
        )
    walls = [Wall(points=[frac(x, y) for x, y in line]) for line in lines if len(line) >= 2]

    portals = []
    for p in raw.portals:
        a, b = frac(p.x1, p.y1), frac(p.x2, p.y2)
        if a != b:
            portals.append(Portal(a=a, b=b))
    lights = [Light(at=frac(light.x, light.y), tier=light.tier) for light in raw.lights]
    return walls, portals, lights


def to_grid(point: Point, map_size: MapSize) -> tuple[float, float]:
    """A point in grid squares on a map of `map_size`."""
    return point.fx * map_size.width, point.fy * map_size.height


def to_pixels(point: Point, image_size: tuple[int, int]) -> tuple[float, float]:
    """A point in pixels on an image of `image_size` (width, height)."""
    return point.fx * image_size[0], point.fy * image_size[1]
