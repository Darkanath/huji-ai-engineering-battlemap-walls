"""The user's preview: the result drawn over a copy of the map."""

import numpy as np
from PIL import Image

from app.domain import Light, MapSize, Point, Portal, TraceResult, Usage, Wall
from app.progress import BoardSnapshot
from app.render import chunk_overlay, overlay
from llm.merge import chunk_layout, seams
from llm.orchestrator import ChunkState
from llm.review import ReviewState


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


# --- The chunked pass's board and untraced parts (feature 002) --------------------------------


def board_snapshot(states, review=ReviewState.waiting):
    """A 2 x 2 board on a 10 x 10 map with the given chunk states."""
    layout = chunk_layout((10, 10), 5, 1, 4)
    found = seams(layout, (10, 10), 1.0)
    return BoardSnapshot(tuple(layout), tuple(found), tuple(states), review)


def test_chunk_overlay_fills_each_part_by_state_and_leaves_the_input_alone():
    """Waiting grey, tracing blue, done green, failed red: each core takes its state's tint."""
    image = Image.new("RGB", (400, 400), (90, 90, 90))
    before = image.tobytes()
    states = (ChunkState.waiting, ChunkState.tracing, ChunkState.done, ChunkState.failed)
    out = chunk_overlay(image, board_snapshot(states), (10, 10))
    assert image.tobytes() == before
    px = np.array(out).astype(int)
    tints = {
        "tracing": px[60, 300],  # part 2, top right, away from its number and outline
        "done": px[300, 60],  # part 3
        "failed": px[300, 300],  # part 4
    }
    assert tints["tracing"][2] > 120 and tints["tracing"][0] < 90  # bluer
    assert tints["done"][1] > 120 and tints["done"][0] < 90  # greener
    assert tints["failed"][0] > 120 and tints["failed"][1] < 90  # redder
    waiting = px[60, 60]
    assert abs(waiting[0] - waiting[2]) < 10  # still grey


def test_chunk_overlay_draws_the_strips_only_while_reviewing():
    """The seam strips are amber while the orchestrator reviews, and not before."""
    image = Image.new("RGB", (400, 400), (90, 90, 90))
    done = (ChunkState.done,) * 4
    on_seam = (120, 190)  # (row, column): y = 3, x = 4.75: in the x = 5 strip, off the outlines
    before = np.array(chunk_overlay(image, board_snapshot(done), (10, 10))).astype(int)[on_seam]
    during = np.array(
        chunk_overlay(image, board_snapshot(done, ReviewState.reviewing), (10, 10))
    ).astype(int)[on_seam]
    assert during[0] > before[0] and during[2] < before[2]


def test_overlay_outlines_untraced_parts_in_grey():
    """A result's untraced part is outlined; its inside is untouched."""
    res = result().model_copy(update={"untraced": [(Point(fx=0.5, fy=0), Point(fx=1, fy=0.5))]})
    out = np.array(overlay(plain(), res)).astype(int)
    edge = out[100, 200]  # on x = 0.5, halfway down the part
    assert tuple(edge) != (90, 90, 90) and abs(edge[0] - edge[2]) < 10
    assert tuple(out[150, 300]) == (90, 90, 90)  # inside the part, off the wall at fy = 0.25
