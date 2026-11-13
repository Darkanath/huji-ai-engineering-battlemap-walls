"""The functions behind the page, without a browser and without a model call."""

import base64
import io

import anthropic
import pytest
from PIL import Image

from app import service
from app.config import load_settings
from app.domain import (
    Light,
    MapSize,
    MapSizeSource,
    PassKind,
    Point,
    TraceResult,
    Usage,
    Wall,
)
from app.errors import (
    DETECTED,
    EARLIER_MASK,
    EMPTY_MASK,
    NO_GRID,
    NOT_SQUARE,
    FailureKind,
    MapSizeInvalid,
    PassFailure,
    UploadRejected,
)
from data.rasterize import load_uvtt

QUICK, DEEP = PassKind.quick, PassKind.deep


@pytest.fixture(scope="module")
def settings():
    """The shipped settings."""
    return load_settings()


@pytest.fixture
def upload(tmp_path):
    """A 700 x 700 PNG on disk, as the page would hand it over."""
    path = tmp_path / "tavern.png"
    Image.new("RGB", (700, 700), (90, 90, 90)).save(path)
    return path


@pytest.fixture
def session(upload, settings):
    """A fresh session for the upload; its temp folder is removed afterwards."""
    s = service.prepare(upload, settings)
    yield s
    service.close(s)


def make_result(
    kind=QUICK,
    size=None,
    source=MapSizeSource.default,
    empty=False,
) -> TraceResult:
    """A TraceResult with one wall and one light (or nothing), as a pass would return."""
    size = size or MapSize(width=25, height=25)
    return TraceResult(
        walls=[] if empty else [Wall(points=[Point(fx=0.5, fy=0.5), Point(fx=0.9, fy=0.5)])],
        lights=[] if empty else [Light(at=Point(fx=0.5, fy=0.5), tier="large")],
        note="Unsure about the door.",
        kind=kind,
        model_id="claude-sonnet-5-5" if kind == QUICK else "claude-opus-5-5",
        effort="medium",
        elapsed_s=21.4,
        usage=Usage(input_tokens=1000),
        cost_usd=0.081,
        traced_size=size,
        size_source=source,
    )


def failure(kind=FailureKind.network, of=QUICK) -> PassFailure:
    """A failed pass."""
    return PassFailure(kind=kind, kind_of_pass=of, cost_usd=0.01, detail="test")


def run(session, outcome, kind=QUICK) -> service.PassTicket:
    """Begin a pass and finish it with `outcome`; returns the ticket."""
    ticket = service.begin_pass(session, kind)
    assert ticket is not None
    assert service.finish_pass(session, ticket, outcome)
    return ticket


# --- Upload --------------------------------------------------------------------------------


@pytest.mark.parametrize("suffix", [".png", ".jpg", ".jpeg", ".webp", ".PNG"])
def test_prepare_accepts_the_three_image_types(tmp_path, settings, suffix):
    """Each allowed type gives a fresh session: 25 x 25, detect on, no mask."""
    path = tmp_path / f"map{suffix}"
    fmt = {".png": "PNG", ".jpg": "JPEG", ".jpeg": "JPEG", ".webp": "WEBP"}[suffix.lower()]
    Image.new("RGB", (100, 100)).save(path, format=fmt)
    s = service.prepare(path, settings)
    assert s.map_size == MapSize(width=25, height=25) and s.size_source == MapSizeSource.default
    assert s.detect_size and s.result is None and s.token and s.tmp_dir.is_dir()
    service.close(s)


def test_prepare_rejects_a_gif(tmp_path, settings):
    """A .gif is the wrong type."""
    path = tmp_path / "map.gif"
    Image.new("RGB", (10, 10)).save(path)
    with pytest.raises(UploadRejected) as err:
        service.prepare(path, settings)
    assert err.value.reason == "wrong_type"


def test_prepare_rejects_a_file_over_the_limit(tmp_path, settings):
    """A file over 20 MB is refused before it is opened."""
    path = tmp_path / "huge.png"
    with path.open("wb") as f:
        f.truncate(20 * 1024 * 1024 + 1)
    with pytest.raises(UploadRejected) as err:
        service.prepare(path, settings)
    assert err.value.reason == "too_large"


def test_prepare_rejects_text_renamed_png(tmp_path, settings):
    """A text file with an image name is not an image."""
    path = tmp_path / "notes.png"
    path.write_text("not an image")
    with pytest.raises(UploadRejected) as err:
        service.prepare(path, settings)
    assert err.value.reason == "not_an_image"


def test_rejected_upload_creates_no_client(tmp_path, settings, monkeypatch):
    """Validation happens before anything could reach the model."""
    monkeypatch.setattr(anthropic, "Anthropic", lambda *a, **k: pytest.fail("client created"))
    path = tmp_path / "map.gif"
    path.write_bytes(b"GIF89a")
    with pytest.raises(UploadRejected):
        service.prepare(path, settings)


def test_a_new_upload_is_a_new_session(upload, settings, session):
    """A second upload gets a new token and no mask."""
    run(session, make_result())
    again = service.prepare(upload, settings)
    assert again.token != session.token and again.result is None
    service.close(again)


# --- Fast pass, preview, export, status (US1) ---------------------------------------------


def test_finished_pass_puts_the_mask_on_the_session(session):
    """A successful pass becomes the mask on screen."""
    result = make_result()
    run(session, result)
    assert session.result == result and session.running is None


def test_preview_is_an_image_of_the_upload_size(session):
    """The preview is the upload, with or without a mask."""
    assert service.preview(session).size == (700, 700)
    run(session, make_result())
    assert service.preview(session).size == (700, 700)


def test_export_writes_the_named_file_in_the_temp_folder(session):
    """The download is <image name><extension> inside the session's folder."""
    run(session, make_result())
    path = service.export(session)
    assert path == session.tmp_dir / "tavern.dd2vtt"
    service.set_extension(session, ".uvtt")
    assert service.export(session).name == "tavern.uvtt"
    assert load_uvtt(path)["resolution"]["map_size"] == {"x": 25, "y": 25}


def test_export_without_a_mask_raises(session):
    """There is nothing to download before a pass."""
    with pytest.raises(ValueError):
        service.export(session)


def test_status_line_names_model_time_cost_and_counts(session):
    """The status line has the model label, effort, seconds, cost, counts and the note."""
    assert service.status_line(session) == ""
    run(session, make_result())
    line = service.status_line(session)
    assert line.startswith("Sonnet 5.5 (medium) · 21 s · about $0.08 · 1 wall, 0 portals, 1 light")
    assert line.endswith("Unsure about the door.")


def test_empty_mask_shows_the_notice_and_can_be_accepted(session):
    """A pass that found nothing is a result: the notice shows and export still works."""
    run(session, make_result(empty=True))
    assert service.result_message(session) == EMPTY_MASK
    assert load_uvtt(service.export(session))["line_of_sight"] == []


def test_close_removes_the_folder_and_is_safe_twice(session):
    """Closing removes the temp folder; a second close does nothing."""
    service.close(session)
    assert not session.tmp_dir.exists()
    service.close(session)


# --- Deep pass (US2) -----------------------------------------------------------------------


def test_deep_needs_a_mask(session):
    """The deeper examination is offered only once a mask exists."""
    assert service.can_start(session, QUICK) and not service.can_start(session, DEEP)
    run(session, make_result())
    assert service.can_start(session, DEEP)


def test_deep_pass_replaces_the_mask(session):
    """A deep result replaces the earlier mask, and the status shows Opus."""
    run(session, make_result())
    deep = make_result(kind=DEEP)
    run(session, deep, DEEP)
    assert session.result == deep
    assert service.status_line(session).startswith("Opus 5.5 (medium)")


def test_button_labels_come_from_the_config(settings):
    """Each button shows its expected time and cost."""
    labels = service.button_labels(settings)
    assert labels[QUICK] == "Suggest walls (about 25 s, about $0.10)"
    assert labels[DEEP] == "Deeper examination (about 70 s, about $0.32)"


# --- Running and failing (US3) -------------------------------------------------------------


def test_failure_keeps_the_mask_and_the_status(session):
    """A failed pass records the failure, keeps the mask and the last good status."""
    run(session, make_result())
    status = service.status_line(session)
    run(session, failure(of=DEEP), DEEP)
    assert session.result is not None and session.running is None
    assert session.last_failure.kind == FailureKind.network
    assert service.status_line(session) == status
    assert service.result_message(session).endswith(EARLIER_MASK)


def test_failure_without_a_mask_has_no_reminder(session):
    """With no mask, the failure message does not mention one."""
    run(session, failure(FailureKind.missing_key))
    assert EARLIER_MASK not in service.result_message(session)
    assert service.begin_pass(session, QUICK) is not None  # a new pass can start after it


def test_stale_ticket_changes_nothing(upload, settings, session):
    """A result for a session replaced by a new upload is dropped."""
    ticket = service.begin_pass(session, QUICK)
    newer = service.prepare(upload, settings)
    assert service.finish_pass(newer, ticket, make_result()) is False
    assert newer.result is None and newer.running is None
    assert service.can_start(newer, QUICK)  # the new image can be traced at once
    service.close(newer)


def test_no_second_pass_while_one_runs(session):
    """Both pass buttons are locked while a pass runs."""
    run(session, make_result())
    assert service.begin_pass(session, QUICK) is not None
    assert service.begin_pass(session, QUICK) is None
    assert service.begin_pass(session, DEEP) is None


def test_export_works_while_a_pass_runs(session):
    """The mask on screen can be accepted during a pass."""
    run(session, make_result())
    service.begin_pass(session, DEEP)
    assert service.export(session).exists()


# --- Map size worked out by the model (US4) ------------------------------------------------


def test_detect_option_sends_no_size(session):
    """With detection on, the ticket carries no size and the fields as fallback."""
    ticket = service.begin_pass(session, QUICK)
    assert ticket.map_size is None and ticket.fallback_size == MapSize(width=25, height=25)


def test_detected_size_fills_the_fields(session):
    """A detected size is applied, marked, and the option turns off."""
    run(session, make_result(size=MapSize(width=26, height=28), source=MapSizeSource.detected))
    assert session.map_size == MapSize(width=26, height=28)
    assert session.size_source == MapSizeSource.detected
    assert not session.detect_size and session.size_note == DETECTED


def test_no_grid_keeps_the_size_and_says_so(session):
    """No grid found: the size stays, and the note explains."""
    run(session, make_result(source=MapSizeSource.not_found))
    assert session.map_size == MapSize(width=25, height=25)
    assert session.size_note == NO_GRID


def test_typed_size_turns_detection_off(session):
    """Typing a size switches detection off; the next ticket carries that size."""
    service.set_map_size(session, 30, 30)
    assert not session.detect_size
    assert service.begin_pass(session, QUICK).map_size == MapSize(width=30, height=30)


def test_size_typed_during_a_pass_wins_over_the_detected_one(session):
    """A size typed while the pass ran is not overwritten."""
    ticket = service.begin_pass(session, QUICK)
    service.set_map_size(session, 30, 30)
    detected = make_result(size=MapSize(width=26, height=28), source=MapSizeSource.detected)
    service.finish_pass(session, ticket, detected)
    assert session.map_size == MapSize(width=30, height=30)
    assert session.size_source == MapSizeSource.typed


def test_deep_after_detection_uses_the_size_on_screen(session):
    """After a detection, a deep pass traces on the detected size unless detection is asked."""
    run(session, make_result(size=MapSize(width=26, height=28), source=MapSizeSource.detected))
    ticket = service.begin_pass(session, DEEP)
    assert ticket.map_size == MapSize(width=26, height=28)
    service.finish_pass(session, ticket, failure(of=DEEP))
    service.set_detect(session, True)
    assert service.begin_pass(session, DEEP).map_size is None


def test_failed_pass_leaves_the_size_alone(session):
    """A failure changes neither the size nor the option."""
    run(session, failure())
    assert session.map_size == MapSize(width=25, height=25) and session.detect_size


# --- Correcting the map size (US5) ---------------------------------------------------------


def test_size_change_keeps_the_mask_and_rescales_the_export(session, monkeypatch):
    """A new size keeps the mask and preview, makes no call, and rescales the file."""
    monkeypatch.setattr(anthropic, "Anthropic", lambda *a, **k: pytest.fail("client created"))
    run(session, make_result())
    before_result, before_preview = session.result, service.preview(session).tobytes()
    service.set_map_size(session, 26, 28)
    assert session.result is before_result
    assert service.preview(session).tobytes() == before_preview
    payload = load_uvtt(service.export(session))
    assert payload["resolution"]["map_size"] == {"x": 26, "y": 28}
    assert payload["line_of_sight"][0][0] == {"x": 13.0, "y": 14.0}
    assert payload["lights"][0]["range"] == 16.0  # the tier is kept
    embedded = Image.open(io.BytesIO(base64.b64decode(payload["image"])))
    assert embedded.size == (1820, 1960)


@pytest.mark.parametrize(("w", "h"), [(0, 10), (201, 10), (2.5, 10), ("", 10), (None, 10)])
def test_invalid_size_is_refused_and_changes_nothing(session, w, h):
    """Out of range, fractional or empty sizes raise the range message."""
    with pytest.raises(MapSizeInvalid) as err:
        service.set_map_size(session, w, h)
    assert err.value.message == "Map width and height must be whole numbers from 1 to 200."
    assert session.map_size == MapSize(width=25, height=25) and session.detect_size


def test_whole_float_size_is_accepted(session):
    """26.0 from a number field is 26."""
    service.set_map_size(session, 26.0, 26.0)
    assert session.map_size == MapSize(width=26, height=26)


def test_non_square_cells_warn_but_apply(session):
    """A size far from the image's proportions warns, and is still used."""
    assert service.set_map_size(session, 25, 25) is None
    assert service.set_map_size(session, 20, 30) == NOT_SQUARE
    assert session.map_size == MapSize(width=20, height=30)
