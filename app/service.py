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
from app.domain import MapSize, MapSizeSource, PassKind, TraceResult
from app.errors import (
    DETECTED,
    EMPTY_MASK,
    NO_GRID,
    NOT_SQUARE,
    MapSizeInvalid,
    PassFailure,
    UploadRejected,
    message,
)
from app.logging import log_event

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
    detect_size: bool = True
    size_note: str = ""  # "Detected from the image", no grid found, or the proportions warning
    size_version: int = 0  # goes up whenever the user types a size
    result: TraceResult | None = None
    last_failure: PassFailure | None = None
    running: PassKind | None = None
    started_at: float | None = None
    extension: str = ".dd2vtt"


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


def can_start(session: Session | None, kind: PassKind) -> bool:
    """Whether a pass of `kind` may start: an image, nothing running, and for deep a mask."""
    if session is None or session.running is not None:
        return False
    return kind == PassKind.quick or session.result is not None


def begin_pass(session: Session, kind: PassKind) -> PassTicket | None:
    """Mark a pass as running and return its ticket, or None if it may not start now."""
    if not can_start(session, kind):
        return None
    now = time.monotonic()
    session.running, session.started_at = kind, now
    return PassTicket(
        token=session.token,
        kind=kind,
        started_at=now,
        map_size=None if session.detect_size else session.map_size,
        fallback_size=session.map_size,
        size_source=session.size_source,
        size_version=session.size_version,
    )


def finish_pass(session: Session, ticket: PassTicket, outcome: TraceResult | PassFailure) -> bool:
    """Apply a pass's outcome; False (and nothing changes) if a new upload replaced the session.

    A failure is recorded and the earlier mask kept. A success replaces the mask; a detected
    size is applied unless the user typed one while the pass ran; no grid found keeps the size
    and sets the note.
    """
    if ticket.token != session.token:
        log_event("pass_dropped", profile=ticket.kind.value, cost_usd=outcome.cost_usd)
        return False
    session.running = session.started_at = None
    if isinstance(outcome, PassFailure):
        session.last_failure = outcome
        return True
    session.result, session.last_failure = outcome, None
    typed_meanwhile = session.size_version != ticket.size_version
    if outcome.size_source == MapSizeSource.detected and not typed_meanwhile:
        session.map_size = outcome.traced_size
        session.size_source = MapSizeSource.detected
        session.detect_size = False
        session.size_note = DETECTED
    elif outcome.size_source == MapSizeSource.not_found and not typed_meanwhile:
        session.size_source = MapSizeSource.not_found
        session.size_note = NO_GRID
    return True


def elapsed(session: Session) -> float:
    """Seconds since the running pass started (0 when none is running)."""
    return 0.0 if session.started_at is None else time.monotonic() - session.started_at


def preview(session: Session) -> Image.Image:
    """The upload, with the mask drawn over it when there is one."""
    return render.overlay(session.image, session.result)


def set_extension(session: Session, extension: str) -> None:
    """Choose .dd2vtt or .uvtt for the download (anything else is ignored)."""
    if extension in EXTENSIONS:
        session.extension = extension


def export(session: Session) -> Path:
    """Write the mask on screen to the session's temp folder; returns the file's path.

    Uses the map size on screen. Raises ValueError when there is no mask (the page only
    offers the download when there is one).
    """
    if session.result is None:
        raise ValueError("there is no mask to export")
    payload = exporter.build(session.result, session.map_size, session.image, session.settings)
    return exporter.write(session.tmp_dir / f"{session.image_name}{session.extension}", payload)


def status_line(session: Session | None) -> str:
    """Model, effort, time, cost and counts of the last successful pass, then its note."""
    if session is None or session.result is None:
        return ""
    r = session.result
    label = session.settings.profiles[r.kind].label
    line = f"{label} ({r.effort}) · {r.elapsed_s:.0f} s · about ${r.cost_usd:.2f} · {r.counts()}"
    return f"{line}\n{r.note}" if r.note else line


def result_message(session: Session | None) -> str:
    """The message area: the last failure's text, or the empty-mask notice, or nothing."""
    if session is None:
        return ""
    if session.last_failure is not None:
        return message(session.last_failure.kind, has_earlier_mask=session.result is not None)
    if session.result is not None and session.result.is_empty():
        return EMPTY_MASK
    return ""


def button_labels(settings: Settings) -> dict[PassKind, str]:
    """The two pass buttons' labels, with expected time and cost from the config."""

    def label(name: str, kind: PassKind) -> str:
        """One button's label."""
        p = settings.profiles[kind]
        return f"{name} (about {p.expected_seconds:.0f} s, about ${p.expected_cost_usd:.2f})"

    return {
        PassKind.quick: label("Suggest walls", PassKind.quick),
        PassKind.deep: label("Deeper examination", PassKind.deep),
    }


def close(session: Session | None) -> None:
    """Remove the session's temp folder; safe to call more than once."""
    if session is not None:
        shutil.rmtree(session.tmp_dir, ignore_errors=True)
