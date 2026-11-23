"""The app's logic, apart from the UI: one `Session` per browser session and the functions the
page calls. None of them calls the model; `app.tracer.run_pass` does, between `begin_pass` and
`finish_pass`. Contract: `specs/001-battlemap-tracer-app/contracts/service.md`.

Only `UploadRejected` and `MapSizeInvalid` are raised for user input, each with a ready message.
"""

import math
import shutil
import tempfile
import time
import uuid
from dataclasses import dataclass, field
from pathlib import Path

from PIL import Image, UnidentifiedImageError

from app import exporter, render
from app.config import Settings
from app.domain import AgentChoice, MapSize, MapSizeSource, PassKind, TraceResult
from app.errors import (
    EMPTY_MASK,
    LIMIT,
    NO_GRID,
    NOT_SQUARE,
    SEAMS_NOT_CHECKED,
    MapSizeInvalid,
    PassFailure,
    UploadRejected,
    detected_note,
    message,
    partial_message,
    short_reason,
)
from app.logging import log_event
from app.progress import ChunkBoard
from llm.merge import seams
from llm.orchestrator import ChunkState
from llm.review import ReviewState

IMAGE_TYPES = (".png", ".jpg", ".jpeg", ".webp")
EXTENSIONS = (".dd2vtt", ".uvtt")
SQUARE_TOLERANCE = 0.05  # cells whose width and height differ by more than this are "not square"


@dataclass
class Session:
    """What one browser session holds: the upload, the map size, the mask and any pass running."""

    settings: Settings
    image: Image.Image
    image_name: str
    tmp_dir: Path
    map_size: MapSize
    token: str = field(default_factory=lambda: uuid.uuid4().hex)
    size_source: MapSizeSource = MapSizeSource.default
    detect_size: bool = False  # set from [app] detect_size_default by prepare()
    size_note: str = ""  # "Detected from the image", no grid found, or the proportions warning
    size_version: int = 0  # goes up whenever the user types a size
    result: TraceResult | None = None
    last_failure: PassFailure | None = None
    running: PassKind | None = None
    started_at: float | None = None
    extension: str = ".dd2vtt"
    result_version: int = 0  # goes up with each new mask
    # The last export file and what it was built from, so it is rebuilt only on a change.
    export_key: tuple | None = None
    export_path: Path | None = None
    # The chunked pass: the selector's value, and the live board while that pass runs.
    agents: AgentChoice | None = None  # set from [chunked].default_agents by prepare()
    board: ChunkBoard | None = None


@dataclass(frozen=True)
class PassTicket:
    """What a pass needs to run, and what `finish_pass` checks it against."""

    token: str
    kind: PassKind
    started_at: float
    map_size: MapSize | None  # None: the model works the size out first
    fallback_size: MapSize
    size_source: MapSizeSource
    size_version: int
    agents: AgentChoice | None = None  # the chunked pass's agents; None for the other passes


def prepare(path: str | Path, settings: Settings) -> Session:
    """Check an upload and start a fresh session for it; no model call.

    Raises UploadRejected for a wrong type, a file over the size limit, or a file that does
    not open as an image.
    """
    path = Path(path)
    limit_mb = settings.app.max_upload_mb
    if path.suffix.lower() not in IMAGE_TYPES:
        raise UploadRejected("wrong_type", limit_mb)
    if path.stat().st_size > limit_mb * 1024 * 1024:
        raise UploadRejected("too_large", limit_mb)
    try:
        with Image.open(path) as img:
            image = img.convert("RGB")
    except (UnidentifiedImageError, OSError, ValueError, Image.DecompressionBombError) as error:
        raise UploadRejected("not_an_image", limit_mb) from error
    app = settings.app
    return Session(
        settings=settings,
        image=image,
        image_name=path.stem,
        tmp_dir=Path(tempfile.mkdtemp(prefix="battlemap-")),
        map_size=MapSize(width=app.default_width, height=app.default_height),
        detect_size=app.detect_size_default,
        agents=settings.chunked.default_agents,
    )


def _whole(value) -> int | None:
    """`value` as an int if it is a whole number (26 or 26.0), else None."""
    if isinstance(value, bool) or value is None or value == "":
        return None
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    return int(number) if math.isfinite(number) and number.is_integer() else None


def check_map_size(width, height, settings: Settings) -> MapSize:
    """A valid MapSize from the fields' values, or MapSizeInvalid with the range message."""
    low, high = settings.app.min_squares, settings.app.max_squares
    w, h = _whole(width), _whole(height)
    if w is None or h is None or not (low <= w <= high and low <= h <= high):
        raise MapSizeInvalid(low, high)
    return MapSize(width=w, height=h)


def proportions_warning(image: Image.Image, size: MapSize) -> str | None:
    """The warning when `size` would make the grid squares visibly non-square, else None."""
    cell_w, cell_h = image.width / size.width, image.height / size.height
    if abs(cell_w - cell_h) / max(cell_w, cell_h) > SQUARE_TOLERANCE:
        return NOT_SQUARE
    return None


def set_map_size(session: Session, width, height) -> str | None:
    """Apply a size the user typed; no model call, and the mask stays where it is.

    Raises MapSizeInvalid (and changes nothing) for anything but whole numbers in range. The
    size becomes `typed`, which wins over detection, so the detect option turns off. Returns
    the proportions warning, if any; it does not block.
    """
    size = check_map_size(width, height, session.settings)
    session.map_size = size
    session.size_source = MapSizeSource.typed
    session.detect_size = False
    session.size_version += 1
    warning = proportions_warning(session.image, size)
    session.size_note = warning or ""
    return warning


def set_detect(session: Session, on: bool) -> None:
    """Turn the "detect map size from the image" option on or off."""
    session.detect_size = bool(on)


def set_agents(session: Session, choice: str) -> None:
    """Pick the chunked pass's agents' model (the selector); anything else is ignored."""
    if choice in session.settings.chunked.agents:
        session.agents = choice


def can_start(session: Session | None, kind: PassKind) -> bool:
    """Whether a pass of `kind` may start: an image, nothing running, and for deep a mask.

    The chunked pass starts like the fast one: it needs no earlier mask.
    """
    if session is None or session.running is not None:
        return False
    return kind in (PassKind.quick, PassKind.chunked) or session.result is not None


def begin_pass(session: Session, kind: PassKind) -> PassTicket | None:
    """Mark a pass as running and return its ticket, or None if it may not start now."""
    if not can_start(session, kind):
        return None
    now = time.monotonic()
    session.running, session.started_at = kind, now
    if kind == PassKind.chunked:
        chunked = session.settings.chunked
        size = session.map_size.as_tuple()
        layout = chunked.layout(size)
        session.board = ChunkBoard(layout, seams(layout, size, chunked.review.strip_squares))
    return PassTicket(
        token=session.token,
        kind=kind,
        started_at=now,
        map_size=None if session.detect_size else session.map_size,
        fallback_size=session.map_size,
        size_source=session.size_source,
        size_version=session.size_version,
        agents=session.agents if kind == PassKind.chunked else None,
    )


def finish_pass(
    session: Session | None, ticket: PassTicket, outcome: TraceResult | PassFailure
) -> bool:
    """Apply a pass's outcome; False (and nothing changes) if the session was replaced by a
    new upload or cleared (`session` is None) while the pass ran. The drop is logged with cost.

    A failure is recorded and the earlier mask kept. A success replaces the mask. Only when the
    pass looked for the size (the ticket had none): a detected size is applied unless the user
    typed one while the pass ran, and no grid found keeps the size and sets the note.
    """
    if session is None or ticket.token != session.token:
        log_event("pass_dropped", profile=ticket.kind.value, cost_usd=outcome.cost_usd)
        return False
    session.running = session.started_at = None
    session.board = None
    if isinstance(outcome, PassFailure):
        session.last_failure = outcome
        return True
    session.result, session.last_failure = outcome, None
    session.result_version += 1
    if ticket.map_size is not None or session.size_version != ticket.size_version:
        return True  # no detection ran, or the user's typed size wins
    if outcome.size_source == MapSizeSource.detected:
        session.map_size = outcome.traced_size
        session.size_source = MapSizeSource.detected
        session.detect_size = False
        size = outcome.traced_size
        session.size_note = detected_note(size.width, size.height, session.image.width)
    elif outcome.size_source == MapSizeSource.not_found:
        session.size_source = MapSizeSource.not_found
        session.size_note = NO_GRID
    return True


def elapsed(session: Session) -> float:
    """Seconds since the running pass started (0 when none is running)."""
    return 0.0 if session.started_at is None else time.monotonic() - session.started_at


def preview(session: Session) -> Image.Image:
    """The upload, with the mask drawn over it when there is one; while a chunked pass runs,
    the upload with its parts tinted by state instead (the board)."""
    board = session.board
    if session.running == PassKind.chunked and board is not None:
        snap = board.snapshot()
        extent = (max(c.core[2] for c in snap.layout), max(c.core[3] for c in snap.layout))
        return render.chunk_overlay(session.image, snap, extent)
    return render.overlay(session.image, session.result)


def progress_line(session: Session) -> str:
    """ "Working… 12 s", plus the parts done and the borders check for a chunked pass."""
    line = f"Working… {elapsed(session):.0f} s"
    board = session.board
    if session.running == PassKind.chunked and board is not None:
        line += f" · {board.done_count()} of {board.total} parts done"
        if board.snapshot().review == ReviewState.reviewing:
            line += " · checking the borders"
    return line


AGENT_TABLE_HEADERS = [
    "Part",
    "State",
    "Time",
    "Cost",
    "Closer views",
    "Walls",
    "Doors/windows",
    "Lights",
]


def _state_text(state: str, failure: str | None) -> str:
    """ "done", "failed: timed out", "skipped: limit reached"."""
    if failure is None:
        return str(state)
    reason = short_reason(failure)
    return reason if failure == LIMIT else f"{state}: {reason}"


def _review_text(review) -> str:
    """The borders row's State column."""
    if review.state == ReviewState.done:
        removed, added = sum(review.removed.values()), sum(review.added.values())
        return f"done: {removed} removed, {added} added"
    if review.state == ReviewState.not_needed:
        return "not needed (one part)"
    return f"not checked: {short_reason(review.failure) or 'stopped'}"


def agent_table(session: Session | None) -> list[list] | None:
    """One row per agent and a last row for the borders check, for the last chunked result;
    None when the result is not from a chunked pass (spec FR-019). Columns:
    `AGENT_TABLE_HEADERS`."""
    if session is None or session.result is None or session.result.kind != PassKind.chunked:
        return None
    r = session.result
    rows = [
        [
            f"Part {c.part}",
            _state_text(c.state, c.failure),
            f"{c.seconds:.0f} s",
            f"${c.cost_usd:.2f}",
            c.views,
            c.walls,
            c.portals,
            c.lights,
        ]
        for c in r.chunks
    ]
    if r.review is not None:
        review = r.review
        rows.append(
            [
                f"Borders ({review.model_label})",
                _review_text(review),
                f"{review.seconds:.0f} s",
                f"${review.cost_usd:.2f}",
                "",
                "",
                "",
                "",
            ]
        )
    return rows


def set_extension(session: Session, extension: str) -> None:
    """Choose .dd2vtt or .uvtt for the download (anything else is ignored)."""
    if extension in EXTENSIONS:
        session.extension = extension


def export(session: Session) -> Path:
    """Write the mask on screen to the session's temp folder; returns the file's path.

    Uses the map size on screen. The file is rebuilt only when the mask, the map size or the
    extension changed since the last export. Raises ValueError when there is no mask (the
    page only offers the download when there is one).
    """
    if session.result is None:
        raise ValueError("there is no mask to export")
    key = (session.result_version, session.map_size, session.extension)
    if key == session.export_key and session.export_path and session.export_path.exists():
        return session.export_path
    payload = exporter.build(session.result, session.map_size, session.image, session.settings)
    path = exporter.write(session.tmp_dir / f"{session.image_name}{session.extension}", payload)
    session.export_key, session.export_path = key, path
    return path


def status_line(session: Session | None) -> str:
    """Model, effort, time, cost and counts of the last successful pass, then its note."""
    if session is None or session.result is None:
        return ""
    r = session.result
    if r.kind == PassKind.chunked:
        chunked = session.settings.chunked
        agents = chunked.agents[r.agents]
        orchestrator = chunked.agents[agents.orchestrator].label
        n = len(r.chunks)
        who = f"{n} {agents.label} agent{'' if n == 1 else 's'} + {orchestrator} orchestrator"
        line = f"Chunked · {who} · {r.elapsed_s:.0f} s · about ${r.cost_usd:.2f} · {r.counts()}"
    else:
        label = session.settings.profiles[r.kind].label
        line = (
            f"{label} ({r.effort}) · {r.elapsed_s:.0f} s · about ${r.cost_usd:.2f} · {r.counts()}"
        )
    return f"{line}\n{r.note}" if r.note else line


def result_message(session: Session | None) -> str:
    """The message area: the last failure's text, or the empty-mask notice, or nothing."""
    if session is None:
        return ""
    if session.last_failure is not None:
        return message(session.last_failure.kind, has_earlier_mask=session.result is not None)
    if session.result is not None and session.result.is_empty():
        return EMPTY_MASK
    if session.result is not None and session.result.kind == PassKind.chunked:
        return _chunked_message(session.result)
    return ""


def _chunked_message(r: TraceResult) -> str:
    """Untraced parts by number (spec FR-012) and/or the borders not being checked."""
    texts = []
    missing = [c for c in r.chunks if c.state != ChunkState.done]
    if missing:
        failed = [c for c in missing if c.state == ChunkState.failed]
        failure = failed[0].failure if failed else LIMIT
        texts.append(partial_message([c.part for c in missing], len(r.chunks), failure))
    if r.review is not None and r.review.state in (ReviewState.failed, ReviewState.skipped):
        texts.append(SEAMS_NOT_CHECKED)
    return " ".join(texts)


def button_labels(
    settings: Settings,
    map_size: MapSize | None = None,
    detect: bool = False,
    agents: AgentChoice | None = None,
) -> dict[PassKind, str]:
    """The three pass buttons' labels, with expected time and cost from the config.

    The chunked pass's label follows the map size on screen, the detect option and the
    selector (defaults: the config's default size and agents). With detection on it also
    gives the most a pass can take and cost, since the detected size may need more parts
    (spec FR-011). Figures not yet measured say "estimate".
    """

    def label(name: str, kind: PassKind) -> str:
        """One button's label."""
        p = settings.profiles[kind]
        return f"{name} (about {p.expected_seconds:.0f} s, about ${p.expected_cost_usd:.2f})"

    return {
        PassKind.quick: label("Suggest walls", PassKind.quick),
        PassKind.deep: label("Deeper examination", PassKind.deep),
        PassKind.chunked: chunked_label(settings, map_size, detect, agents),
    }


def chunked_label(
    settings: Settings, map_size: MapSize | None, detect: bool, agents: AgentChoice | None
) -> str:
    """ "Chunked pass: 4 Sonnet agents (about 45 s, about $0.29, estimate)"."""
    chunked = settings.chunked
    app = settings.app
    size = map_size or MapSize(width=app.default_width, height=app.default_height)
    agents = agents or chunked.default_agents
    choice = chunked.agents[agents]
    n = len(chunked.layout(size.as_tuple()))
    seconds, cost = chunked.expected(size.as_tuple(), agents, detect, settings.size_step)
    estimate = ", estimate" if choice.estimate else ""
    name = choice.label.split()[0]
    who = f"{n} {name} agent{'' if n == 1 else 's'}"
    figures = f"(about {seconds:.0f} s, about ${cost:.2f}{estimate})"
    if not detect:
        return f"Chunked pass: {who} {figures}"
    top = chunked.max_per_side**2
    label = f"Chunked pass: {who} for {size.width} x {size.height} {figures}"
    if n < top:
        max_s, max_cost = chunked.expected_max(agents, True, settings.size_step)
        label += f"; up to ${max_cost:.2f} and {max_s:.0f} s if the detected size needs {top} parts"
    return label


def close(session: Session | None) -> None:
    """Remove the session's temp folder; safe to call more than once."""
    if session is not None:
        shutil.rmtree(session.tmp_dir, ignore_errors=True)
