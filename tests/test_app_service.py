"""The functions behind the page, without a browser and without a model call."""

import base64
import io

import anthropic
import pytest
from PIL import Image

from app import service, tracer
from app.config import load_settings
from app.domain import (
    ChunkReport,
    Light,
    MapSize,
    MapSizeSource,
    PassKind,
    Point,
    ReviewReport,
    TraceResult,
    Usage,
    Wall,
)
from app.errors import (
    EARLIER_MASK,
    EMPTY_MASK,
    NO_GRID,
    NOT_SQUARE,
    SEAMS_NOT_CHECKED,
    FailureKind,
    MapSizeInvalid,
    PassFailure,
    UploadRejected,
)
from data.rasterize import load_uvtt
from llm.merge import chunk_layout
from llm.orchestrator import ChunkState
from llm.review import ReviewState

from conftest import RoutingFake, call, reply, span, text

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
    """Each allowed type gives a fresh session: 25 x 25, detect off (config), no mask."""
    path = tmp_path / f"map{suffix}"
    fmt = {".png": "PNG", ".jpg": "JPEG", ".jpeg": "JPEG", ".webp": "WEBP"}[suffix.lower()]
    Image.new("RGB", (100, 100)).save(path, format=fmt)
    s = service.prepare(path, settings)
    assert s.map_size == MapSize(width=25, height=25) and s.size_source == MapSizeSource.default
    assert not s.detect_size and s.result is None and s.token and s.tmp_dir.is_dir()
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


@pytest.fixture
def detecting(session):
    """A session with "detect map size from the image" ticked (it starts off)."""
    service.set_detect(session, True)
    return session


def test_detect_option_starts_off_and_sends_the_typed_size(session):
    """By default no detection runs: the ticket carries the size in the fields."""
    assert not session.detect_size
    assert service.begin_pass(session, QUICK).map_size == MapSize(width=25, height=25)


def test_detect_option_sends_no_size(session, detecting):
    """With detection on, the ticket carries no size and the fields as fallback."""
    ticket = service.begin_pass(session, QUICK)
    assert ticket.map_size is None and ticket.fallback_size == MapSize(width=25, height=25)


def test_detected_size_fills_the_fields(session, detecting):
    """A detected size is applied, marked, and the option turns off."""
    run(session, make_result(size=MapSize(width=26, height=28), source=MapSizeSource.detected))
    assert session.map_size == MapSize(width=26, height=28)
    assert session.size_source == MapSizeSource.detected
    assert not session.detect_size
    assert session.size_note.startswith("Detected from the image: 26 x 28 squares, 26.9 px")


def test_no_grid_keeps_the_size_and_says_so(session, detecting):
    """No grid found: the size stays, and the note explains."""
    run(session, make_result(source=MapSizeSource.not_found))
    assert session.map_size == MapSize(width=25, height=25)
    assert session.size_note == NO_GRID


def test_typed_size_turns_detection_off(session, detecting):
    """Typing a size switches detection off; the next ticket carries that size."""
    service.set_map_size(session, 30, 30)
    assert not session.detect_size
    assert service.begin_pass(session, QUICK).map_size == MapSize(width=30, height=30)


def test_size_typed_during_a_pass_wins_over_the_detected_one(session, detecting):
    """A size typed while the pass ran is not overwritten."""
    ticket = service.begin_pass(session, QUICK)
    service.set_map_size(session, 30, 30)
    detected = make_result(size=MapSize(width=26, height=28), source=MapSizeSource.detected)
    service.finish_pass(session, ticket, detected)
    assert session.map_size == MapSize(width=30, height=30)
    assert session.size_source == MapSizeSource.typed


def test_deep_after_detection_uses_the_size_on_screen(session, detecting):
    """After a detection, a deep pass traces on the detected size unless detection is asked."""
    run(session, make_result(size=MapSize(width=26, height=28), source=MapSizeSource.detected))
    ticket = service.begin_pass(session, DEEP)
    assert ticket.map_size == MapSize(width=26, height=28)
    service.finish_pass(session, ticket, failure(of=DEEP))
    service.set_detect(session, True)
    assert service.begin_pass(session, DEEP).map_size is None


def test_failed_pass_leaves_the_size_alone(session, detecting):
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
    assert session.map_size == MapSize(width=25, height=25) and session.size_source == "default"


def test_whole_float_size_is_accepted(session):
    """26.0 from a number field is 26."""
    service.set_map_size(session, 26.0, 26.0)
    assert session.map_size == MapSize(width=26, height=26)


def test_non_square_cells_warn_but_apply(session):
    """A size far from the image's proportions warns, and is still used."""
    assert service.set_map_size(session, 25, 25) is None
    assert service.set_map_size(session, 20, 30) == NOT_SQUARE
    assert session.map_size == MapSize(width=20, height=30)


def test_result_for_a_cleared_session_is_dropped(session):
    """A pass that ends after the upload was cleared is dropped without an error."""
    ticket = service.begin_pass(session, QUICK)
    assert service.finish_pass(None, ticket, make_result()) is False


def test_no_grid_note_only_after_a_pass_that_looked(session):
    """A pass with a given size never sets the no-grid note, even after an earlier one did."""
    service.set_detect(session, True)
    run(session, make_result(source=MapSizeSource.not_found))
    assert session.size_note == NO_GRID
    session.size_note = ""
    service.set_detect(session, False)
    stale = make_result(source=MapSizeSource.not_found)  # the source the ticket carried
    ticket = service.begin_pass(session, QUICK)
    assert ticket.map_size is not None
    service.finish_pass(session, ticket, stale)
    assert session.size_note == ""


def test_export_is_rebuilt_only_on_a_change(session, monkeypatch):
    """Exporting twice with nothing changed builds the file once; a size change rebuilds it."""
    run(session, make_result())
    calls = []
    real = service.exporter.build
    monkeypatch.setattr(service.exporter, "build", lambda *a: calls.append(1) or real(*a))
    service.export(session)
    service.export(session)
    assert len(calls) == 1
    service.set_map_size(session, 30, 30)
    service.export(session)
    assert len(calls) == 2


# --- The chunked pass (feature 002) ----------------------------------------------------------

CHUNKED = PassKind.chunked


def chunked_result(states=("done",) * 4, review="done") -> TraceResult:
    """A chunked pass's result with one report per part and a review report."""
    base = make_result()
    chunks = [
        ChunkReport(
            part=i + 1,
            state=ChunkState(s),
            seconds=20.0 + i,
            cost_usd=0.05,
            views=i,
            walls=2,
            portals=1,
            lights=0,
            failure={"done": None, "failed": "timeout", "skipped": "limit"}[s],
        )
        for i, s in enumerate(states)
    ]
    review_report = ReviewReport(
        state=ReviewState(review),
        model_label="Sonnet 5.5",
        seconds=12.0,
        cost_usd=0.04,
        failure={"done": None, "failed": "refusal", "skipped": "limit", "not_needed": None}[review],
        removed={"walls": 1, "portals": 0, "lights": 0} if review == "done" else {},
        added={"walls": 2, "portals": 0, "lights": 1} if review == "done" else {},
    )
    untraced = [(Point(fx=0.5, fy=0), Point(fx=1, fy=0.5)) for s in states if s != "done"]
    return base.model_copy(
        update={
            "kind": CHUNKED,
            "agents": "sonnet",
            "orchestrator_model": "claude-sonnet-5-5",
            "chunks": chunks,
            "review": review_report,
            "untraced": untraced,
            "cost_usd": 0.27,
            "elapsed_s": 41.0,
        }
    )


def test_set_agents_accepts_only_the_three_choices(session):
    """The selector's value: Sonnet by default, Haiku or Opus when picked, nothing else."""
    assert session.agents == "sonnet"
    service.set_agents(session, "haiku")
    assert session.agents == "haiku"
    service.set_agents(session, "fable")
    assert session.agents == "haiku"


def test_chunked_pass_starts_like_the_fast_one_and_carries_its_board(session):
    """No mask is needed; the ticket names the agents and the session gets a waiting board."""
    assert service.can_start(session, CHUNKED)
    service.set_agents(session, "opus")
    ticket = service.begin_pass(session, CHUNKED)
    assert ticket.agents == "opus"
    assert session.board.total == 4 and session.board.done_count() == 0
    assert not service.can_start(session, CHUNKED)  # one pass at a time
    service.finish_pass(session, ticket, chunked_result())
    assert session.board is None and session.running is None


def test_chunked_button_label_follows_map_size_choice_and_detection(settings):
    """Chunk count, agents' model, time and cost, marked as an estimate; the existing two
    labels are unchanged; with detection on, the 16-part upper bound is shown too."""
    size = MapSize(width=25, height=25)
    labels = service.button_labels(settings, size, False, "sonnet")
    assert labels[CHUNKED] == "Chunked pass: 4 Sonnet agents (about 45 s, about $0.29, estimate)"
    assert labels[QUICK] == "Suggest walls (about 25 s, about $0.10)"
    assert labels[DEEP] == "Deeper examination (about 70 s, about $0.32)"
    big = service.button_labels(settings, MapSize(width=50, height=50), False, "haiku")
    assert big[CHUNKED].startswith("Chunked pass: 16 Haiku agents (about 140 s, about $0.13")
    detecting = service.button_labels(settings, size, True, "sonnet")[CHUNKED]
    assert "4 Sonnet agents for 25 x 25 (about 53 s, about $0.32, estimate)" in detecting
    assert detecting.endswith("up to $1.04 and 128 s if the detected size needs 16 parts")
    one = service.button_labels(settings, MapSize(width=10, height=10), False, "sonnet")
    assert one[CHUNKED].startswith("Chunked pass: 1 Sonnet agent (about 25 s, about $0.06")


def test_progress_line_counts_parts_then_says_the_borders_are_checked(session):
    """ "Working… N s", then the parts done, then the review."""
    service.begin_pass(session, CHUNKED)
    assert service.progress_line(session).endswith(" · 0 of 4 parts done")
    session.board.update_chunk(0, ChunkState.done)
    session.board.update_chunk(1, ChunkState.done)
    assert service.progress_line(session).endswith(" · 2 of 4 parts done")
    session.board.update_review(ReviewState.reviewing)
    assert service.progress_line(session).endswith(" · checking the borders")
    assert service.progress_line(session).startswith("Working… ")


def test_agent_table_has_a_row_per_part_and_one_for_the_borders(session):
    """FR-019: part, state and reason, time, cost, views and counts; the borders row last."""
    run(session, chunked_result(states=("done", "failed", "done", "skipped")), CHUNKED)
    rows = service.agent_table(session)
    assert len(rows) == 5
    assert rows[0] == ["Part 1", "done", "20 s", "$0.05", 0, 2, 1, 0]
    assert rows[1][:2] == ["Part 2", "failed: timed out"]
    assert rows[3][:2] == ["Part 4", "skipped: limit reached"]
    assert rows[4][:4] == ["Borders (Sonnet 5.5)", "done: 1 removed, 3 added", "12 s", "$0.04"]
    assert service.AGENT_TABLE_HEADERS[0] == "Part"


def test_agent_table_is_none_after_a_single_session_pass(session):
    """The table belongs to the chunked pass only."""
    assert service.agent_table(session) is None
    run(session, make_result())
    assert service.agent_table(session) is None


def test_chunked_status_line_names_agents_orchestrator_time_and_cost(session):
    """The status line of a chunked result."""
    run(session, chunked_result(), CHUNKED)
    line = service.status_line(session)
    assert line.startswith("Chunked · 4 Sonnet 5.5 agents + Sonnet 5.5 orchestrator · 41 s")
    assert "about $0.27" in line


def test_partial_and_unchecked_results_say_so(session):
    """Untraced parts are named by number; an unreviewed result says the borders were not
    checked; a complete one says nothing."""
    run(
        session, chunked_result(states=("done", "failed", "done", "done"), review="failed"), CHUNKED
    )
    text = service.result_message(session)
    assert text.startswith("Part 2 of 4 could not be traced (it took too long).")
    assert SEAMS_NOT_CHECKED in text
    run(session, chunked_result(), CHUNKED)
    assert service.result_message(session) == ""


def test_preview_draws_the_board_while_the_chunked_pass_runs(session):
    """While running, the preview is the map with the parts tinted; afterwards the mask."""
    plain = service.preview(session)
    service.begin_pass(session, CHUNKED)
    session.board.update_chunk(0, ChunkState.tracing)
    running = service.preview(session)
    assert running.tobytes() != plain.tobytes()


def test_a_chunked_pass_runs_from_click_to_file(session, settings):
    """Quickstart step 3: begin, run with a routing fake, finish, export; the file loads with
    the merged counts."""
    windows = [c.window for c in chunk_layout((25, 25), 13, 1, 4)]
    left = {"points": [{"x": 3, "y": 5}, {"x": 13.5, "y": 5}]}
    right = {"points": [{"x": 11.5, "y": 5}, {"x": 22, "y": 5}]}
    door = {"x1": 5, "y1": 20, "x2": 6, "y2": 20}

    def submits(walls=(), portals=()):
        """One agent's script."""
        answer = {"walls": list(walls), "arcs": [], "portals": list(portals), "lights": []}
        return [reply(call("submit_answer", answer)), reply(text("Done."), stop="end_turn")]

    client = RoutingFake(
        {
            span(windows[0]): submits([left]),
            span(windows[1]): submits([right]),
            span(windows[2]): submits(portals=[door]),
            span(windows[3]): submits(),
        }
    )
    ticket = service.begin_pass(session, CHUNKED)
    outcome = tracer.run_pass(
        session.image,
        ticket.map_size,
        ticket.fallback_size,
        CHUNKED,
        settings,
        client,
        ticket.size_source,
        agents=ticket.agents,
        board=session.board,
    )
    assert service.finish_pass(session, ticket, outcome)
    uvtt = load_uvtt(service.export(session))
    assert len(uvtt["line_of_sight"]) == 1 and len(uvtt["portals"]) == 1
    assert len(service.agent_table(session)) == 5
