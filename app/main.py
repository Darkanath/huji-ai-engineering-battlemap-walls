"""The Gradio page: wiring only. Every decision is made in `app/service.py`; the only model call
is `app.tracer.run_pass`, started by the two pass buttons.

Run with: docker compose run --rm --service-ports app python -m app.main (http://localhost:7860)

Gradio 6.32.0 (the version in uv.lock), checked against its installed source and docstrings
on 2026-11-13 before writing this file (research.md R13):

- `gr.State(value=callable, delete_callback=fn)`: the callable runs once per browser session;
  the stored object is handed to every handler by reference (deepcopied only when created),
  so handlers can mutate it without returning it. `delete_callback(value)` runs when the
  session ends (tab closed or refreshed); it is used to remove the session's temp folder.
  `Blocks.unload(fn)` exists too, but its `fn` takes no arguments, so it cannot know which
  session ended.
- `gr.File(file_types=[...], type="filepath")`: with `file_types` set, the server itself
  refuses other types with Gradio's own wording ("Invalid file type…") before any handler
  runs, so it is not set: `service.prepare` checks the type and shows the app's message. The
  handler gets a temp path with the uploaded file's base name. Events: upload, clear.
- `Blocks.launch(max_file_size="20mb", show_error=False, server_name, server_port)`: the
  server refuses larger uploads; with `show_error=False` no exception text reaches the page.
- `gr.DownloadButton(label, value=path, interactive)`: clicking downloads the file at
  `value`; a handler updates it by returning `gr.DownloadButton(value=..., interactive=...)`.
- Components are enabled or disabled by returning `gr.Button(interactive=...)` (or the
  matching class) from a handler; `gr.skip()` leaves an output as it is.
- `gr.Blocks(delete_cache=(frequency_s, age_s))`: Gradio copies uploads and download files
  into its own cache (/tmp/gradio); this removes old ones.
- Generator handlers: each `yield` updates the outputs, which gives the "Working… N s" line.
  Each event listener runs one call at a time by default, and different listeners run
  side by side, so an upload or a map-size change is handled while a pass runs.
- `gr.Number` events include `input`, `blur` and `submit`; `change` also fires when a handler
  sets the value, so it is not used for typed sizes. Its own `minimum`/`maximum` reject a
  value with a raw error before the handler runs, so they are not set: the range check and
  its message are `service.set_map_size`'s.
"""

import functools
import time
from concurrent.futures import Future, ThreadPoolExecutor

import gradio as gr

from app import service, tracer
from app.config import Settings, load_settings
from app.domain import PassKind
from app.errors import FailureKind, MapSizeInvalid, UploadRejected, message
from app.logging import log_event, setup_logging
from app.render import LEGEND

NOTICE = "Your image is sent to Anthropic, a third-party AI provider, for analysis."
DEEP_NOTE = (
    "The fast pass handles ordinary buildings well but often misses cave outlines and doors "
    "in castles and other complex structures. The deeper examination fixes most of that."
)
TICK_S = 1.0  # how often the progress line updates
CACHE_CLEANUP = (1800, 3600)  # Gradio's file cache: check every 30 min, delete after 1 hour
EXECUTOR = ThreadPoolExecutor(max_workers=4, thread_name_prefix="pass")


class Holder:
    """The per-browser-session state: the current Session (None before an upload) and a
    one-off notice for the message area (an upload or map-size problem).

    A plain class, not a dataclass: Gradio tries to serialize a dataclass given as a State's
    initial value. The class itself is that value; Gradio calls it once per browser session.
    """

    def __init__(self) -> None:
        """Start with no upload, no notice, and the size fields untouched."""
        self.session: service.Session | None = None
        self.notice = ""
        # True once the user types in a size field, even the value already shown: a typed
        # size wins over detection, so confirming 25 x 25 by typing it must count.
        self.size_touched = False


def _close(holder: Holder) -> None:
    """Session-end cleanup: remove the temp folder (FR-030)."""
    if holder is not None:
        service.close(holder.session)


def view(holder: Holder) -> tuple:
    """Every output's value for the current state, in the order of `outputs` in `build_ui`."""
    s = holder.session
    labels = service.button_labels(SETTINGS)
    running = s is not None and s.running is not None
    download = None
    if s is not None and s.result is not None:
        try:
            download = str(service.export(s))
        except Exception as error:  # noqa: BLE001 - view() must never fail (safe() calls it)
            log_event("export_failed", detail=type(error).__name__)
            holder.notice = message(FailureKind.unexpected)
    message_text = holder.notice or service.result_message(s)
    return (
        service.preview(s) if s is not None else None,
        service.status_line(s),
        message_text,
        s.size_note if s is not None else "",
        s.map_size.width if s is not None else SETTINGS.app.default_width,
        s.map_size.height if s is not None else SETTINGS.app.default_height,
        s.detect_size if s is not None else SETTINGS.app.detect_size_default,
        gr.Button(labels[PassKind.quick], interactive=service.can_start(s, PassKind.quick)),
        gr.Button(labels[PassKind.deep], interactive=service.can_start(s, PassKind.deep)),
        gr.DownloadButton("Accept mask", value=download, interactive=download is not None),
        "" if not running else gr.skip(),
    )


def safe(handler):
    """Wrap a handler so an unexpected error is logged and shown as a plain message (FR-027)."""

    @functools.wraps(handler)
    def wrapper(holder: Holder, *args):
        """Run the handler; on any exception log it and show the `unexpected` message."""
        try:
            return handler(holder, *args)
        except Exception as error:  # noqa: BLE001 - nothing may reach the page as a trace
            log_event("handler_failed", detail=f"{handler.__name__}: {type(error).__name__}")
            holder.notice = message(FailureKind.unexpected)
            return view(holder)

    return wrapper


def safe_stream(handler):
    """Like `safe`, for generator handlers."""

    @functools.wraps(handler)
    def wrapper(holder: Holder, *args):
        """Yield the handler's updates; on any exception log it and show the message."""
        try:
            yield from handler(holder, *args)
        except Exception as error:  # noqa: BLE001 - nothing may reach the page as a trace
            log_event("handler_failed", detail=f"{handler.__name__}: {type(error).__name__}")
            if holder.session is not None:
                holder.session.running = holder.session.started_at = None
            holder.notice = message(FailureKind.unexpected)
            yield view(holder)

    return wrapper


@safe
def on_upload(holder: Holder, path: str | None) -> tuple:
    """A new upload: validate it, start a fresh session, drop the old one (and its pass)."""
    holder.notice = ""
    if not path:
        return view(holder)
    try:
        new = service.prepare(path, SETTINGS)
    except UploadRejected as rejected:
        holder.notice = rejected.message
        return view(holder)
    service.close(holder.session)
    holder.session, holder.size_touched = new, False
    return view(holder)


@safe
def on_clear(holder: Holder) -> tuple:
    """The upload was removed: back to the empty page."""
    service.close(holder.session)
    holder.session, holder.notice = None, ""
    return view(holder)


@safe
def on_size(holder: Holder, width, height) -> tuple:
    """A typed map size: check it and rebuild the preview and the download; no pass."""
    holder.notice = ""
    s = holder.session
    if s is None:
        return view(holder)
    _apply_size(holder, width, height)
    return view(holder)


def _apply_size(holder: Holder, width, height) -> bool:
    """Apply the size fields if the user typed in them or they differ from the session's.

    Returns False (with the range message as the notice) when the size is invalid.
    """
    s = holder.session
    unchanged = (width, height) == (s.map_size.width, s.map_size.height)
    if unchanged and not holder.size_touched:
        return True
    holder.size_touched = False
    try:
        service.set_map_size(s, width, height)
    except MapSizeInvalid as invalid:
        holder.notice = invalid.message
        return False
    return True


def on_size_typed(holder: Holder) -> None:
    """The user typed in a size field: mark it, so the value counts as typed when applied."""
    if holder is not None:
        holder.size_touched = True


@safe
def on_detect(holder: Holder, on: bool) -> tuple:
    """The detect option was switched by the user."""
    if holder.session is not None:
        service.set_detect(holder.session, on)
    return view(holder)


@safe
def on_extension(holder: Holder, extension: str) -> tuple:
    """The file type changed: rebuild the download under the new name."""
    if holder.session is not None:
        service.set_extension(holder.session, extension)
    return view(holder)


def _progress(seconds: float) -> tuple:
    """Outputs while a pass runs: only the progress line and the locked buttons change."""
    skip = gr.skip()
    locked = gr.Button(interactive=False)
    return (skip,) * 7 + (locked, locked, skip, f"Working… {seconds:.0f} s")


def _pass(holder: Holder, width, height, detect: bool, kind: PassKind):
    """Run one pass in a worker thread, yielding the elapsed time; then show the outcome."""
    holder.notice = ""
    s = holder.session
    if s is None:
        yield view(holder)
        return
    # Apply the option and a size typed just before the click (their events may not have run
    # yet); a typed size turns detection off, as it wins over the detected one.
    service.set_detect(s, detect)
    if not _apply_size(holder, width, height):
        yield view(holder)
        return
    ticket = service.begin_pass(s, kind)
    if ticket is None:
        yield view(holder)
        return
    yield _progress(0)
    future: Future = EXECUTOR.submit(
        tracer.run_pass,
        s.image,
        ticket.map_size,
        ticket.fallback_size,
        kind,
        SETTINGS,
        None,
        ticket.size_source,
    )
    while not future.done():
        if holder.session is not s:
            # A new upload replaced this session: its result will be dropped (and logged)
            # when it arrives; the page already shows the new image.
            future.add_done_callback(
                lambda f: service.finish_pass(holder.session, ticket, f.result())
            )
            yield view(holder)
            return
        time.sleep(TICK_S)
        yield _progress(service.elapsed(s))
    service.finish_pass(holder.session, ticket, future.result())
    yield view(holder)


@safe_stream
def on_quick(holder: Holder, width, height, detect: bool):
    """ "Suggest walls": the fast pass."""
    yield from _pass(holder, width, height, detect, PassKind.quick)


@safe_stream
def on_deep(holder: Holder, width, height, detect: bool):
    """ "Deeper examination": the deep pass, from scratch, replacing the mask."""
    yield from _pass(holder, width, height, detect, PassKind.deep)


def build_ui(settings: Settings) -> gr.Blocks:
    """The page, with every control from contracts/ui.md wired to the handlers above."""
    labels = service.button_labels(settings)
    app = settings.app
    # Gradio keeps uploads and downloads in its own cache too; delete files older than an hour,
    # checked every 30 minutes, so no upload outlives its session for long.
    with gr.Blocks(title="Battlemap Tracer", delete_cache=CACHE_CLEANUP) as page:
        holder = gr.State(Holder, delete_callback=_close)
        gr.Markdown(
            "# Battlemap Tracer\nUpload a top-down battlemap, get its walls, doors, windows "
            "and lights suggested, and download a Universal VTT file for Roll20."
        )
        with gr.Row():
            with gr.Column(scale=1):
                upload = gr.File(
                    label=f"Map image (PNG, JPEG or WebP, up to {app.max_upload_mb:g} MB)",
                    type="filepath",
                )
                gr.Markdown(NOTICE)
                with gr.Row():
                    width = gr.Number(
                        app.default_width,
                        label="Map width (squares)",
                        precision=0,
                    )
                    height = gr.Number(
                        app.default_height,
                        label="Map height (squares)",
                        precision=0,
                    )
                detect = gr.Checkbox(
                    app.detect_size_default,
                    label=(
                        "Detect map size from the image (adds about "
                        f"${settings.size_step.expected_cost_usd:.2f} to the pass)"
                    ),
                )
                size_note = gr.Markdown()
                quick = gr.Button(labels[PassKind.quick], variant="primary", interactive=False)
                deep = gr.Button(labels[PassKind.deep], interactive=False)
                gr.Markdown(DEEP_NOTE)
                progress = gr.Markdown()
                extension = gr.Radio(list(service.EXTENSIONS), value=".dd2vtt", label="File type")
                accept = gr.DownloadButton("Accept mask", interactive=False)
            with gr.Column(scale=2):
                preview = gr.Image(
                    label="Preview", type="pil", interactive=False, buttons=["fullscreen"]
                )
                gr.Markdown(LEGEND)
                status = gr.Markdown()
                notice = gr.Markdown()

        outputs = [
            preview,
            status,
            notice,
            size_note,
            width,
            height,
            detect,
            quick,
            deep,
            accept,
            progress,
        ]
        upload.upload(on_upload, [holder, upload], outputs)
        upload.clear(on_clear, [holder], outputs)
        for field in (width, height):
            field.input(on_size_typed, [holder], None)
        for event in (width.blur, width.submit, height.blur, height.submit):
            event(on_size, [holder, width, height], outputs)
        detect.input(on_detect, [holder, detect], outputs)
        extension.input(on_extension, [holder, extension], outputs)
        quick.click(on_quick, [holder, width, height, detect], outputs)
        deep.click(on_deep, [holder, width, height, detect], outputs)
    return page


SETTINGS = load_settings()


def main() -> None:
    """Start the app on 0.0.0.0:7860 with errors hidden from the page."""
    setup_logging()
    page = build_ui(SETTINGS)
    page.queue().launch(
        server_name="0.0.0.0",
        server_port=7860,
        max_file_size=f"{SETTINGS.app.max_upload_mb:g}mb",
        show_error=False,
    )


if __name__ == "__main__":
    main()
