"""Live state of a running chunked pass, for the page: each chunk's state and the review's.

The orchestrator's callback writes here from worker threads while the page reads it once a
second from the main thread, so every access holds one lock and the page only ever gets a
copy (`snapshot`). Contract: specs/002-chunked-map-tracing/data-model.md (ChunkBoard).
"""

import threading
from dataclasses import dataclass

from llm.merge import Chunk, Seam
from llm.orchestrator import ChunkState
from llm.review import ReviewState


@dataclass(frozen=True)
class BoardSnapshot:
    """A copy of the board at one moment, safe to draw from."""

    layout: tuple[Chunk, ...]
    seams: tuple[Seam, ...]
    states: tuple[ChunkState, ...]
    review: ReviewState


class ChunkBoard:
    """Each chunk's state and the review's, shared between the pass and the page."""

    def __init__(self, layout: list[Chunk], seams: list[Seam]):
        """Start with every chunk waiting; the review waits too, or is not needed (one chunk)."""
        self._lock = threading.Lock()
        self._set(layout, seams)

    def _set(self, layout: list[Chunk], seams: list[Seam]) -> None:
        """Replace the layout and reset every state (caller holds the lock or is __init__)."""
        self._layout, self._seams = tuple(layout), tuple(seams)
        self._states = [ChunkState.waiting] * len(layout)
        self._review = ReviewState.waiting if len(layout) > 1 else ReviewState.not_needed

    def rebuild(self, layout: list[Chunk], seams: list[Seam]) -> None:
        """Switch to a new layout (the size step found another map size); all waiting again."""
        with self._lock:
            self._set(layout, seams)

    def update_chunk(self, index: int, state: ChunkState) -> None:
        """Record a chunk's new state."""
        with self._lock:
            self._states[index] = ChunkState(state)

    def update_review(self, state: ReviewState) -> None:
        """Record the review's new state."""
        with self._lock:
            self._review = ReviewState(state)

    def on_update(self, kind: str, index: int | None, state: str) -> None:
        """The orchestrator's callback (`llm.orchestrator.trace_chunks(on_update=...)`)."""
        if kind == "chunk" and index is not None:
            self.update_chunk(index, ChunkState(state))
        elif kind == "review":
            self.update_review(ReviewState(state))

    def snapshot(self) -> BoardSnapshot:
        """A copy of the current states."""
        with self._lock:
            return BoardSnapshot(self._layout, self._seams, tuple(self._states), self._review)

    def done_count(self) -> int:
        """How many chunks have finished with an answer."""
        with self._lock:
            return sum(s == ChunkState.done for s in self._states)

    @property
    def total(self) -> int:
        """How many chunks the layout has."""
        with self._lock:
            return len(self._states)
