"""The live chunk board the page reads while a chunked pass runs."""

import threading

from app.progress import ChunkBoard
from llm.merge import chunk_layout, seams
from llm.orchestrator import ChunkState
from llm.review import ReviewState


def board(size=(25, 25)) -> ChunkBoard:
    """A board for the default layout of `size`."""
    layout = chunk_layout(size, 13, 1, 4)
    return ChunkBoard(layout, seams(layout, size, 1.0))


def test_a_new_board_has_every_chunk_waiting():
    """Four waiting chunks and a waiting review on a 25 x 25 map; no review for one chunk."""
    b = board()
    snap = b.snapshot()
    assert snap.states == (ChunkState.waiting,) * 4 and snap.review == ReviewState.waiting
    assert b.total == 4 and b.done_count() == 0
    assert board((13, 13)).snapshot().review == ReviewState.not_needed


def test_updates_from_several_threads_all_land():
    """Every worker's update is recorded."""
    b = board((50, 50))
    workers = [
        threading.Thread(target=b.on_update, args=("chunk", i, ChunkState.done)) for i in range(16)
    ]
    for w in workers:
        w.start()
    for w in workers:
        w.join()
    assert b.done_count() == 16


def test_a_snapshot_does_not_change_after_later_updates():
    """The page draws from a copy."""
    b = board()
    snap = b.snapshot()
    b.update_chunk(0, ChunkState.tracing)
    b.on_update("review", None, ReviewState.reviewing)
    assert snap.states[0] == ChunkState.waiting and snap.review == ReviewState.waiting
    assert b.snapshot().states[0] == ChunkState.tracing
    assert b.snapshot().review == ReviewState.reviewing


def test_done_count_counts_only_done():
    """Failed and skipped parts are not done."""
    b = board()
    for i, state in enumerate([ChunkState.done, ChunkState.failed, ChunkState.skipped]):
        b.update_chunk(i, state)
    assert b.done_count() == 1


def test_rebuild_resets_every_state():
    """A new layout (another map size) starts all waiting."""
    b = board()
    b.update_chunk(0, ChunkState.done)
    layout = chunk_layout((50, 50), 13, 1, 4)
    b.rebuild(layout, seams(layout, (50, 50), 1.0))
    assert b.total == 16 and b.done_count() == 0
