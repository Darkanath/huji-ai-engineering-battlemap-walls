# Contract: the functions behind the page

The interface `app/main.py` and the tests call. Plain functions; none of them needs a
browser. Types are in [../data-model.md](../data-model.md). Signatures show intent; exact
names are settled in implementation.

## `app/service.py`

| Function | Does | Model call |
| --- | --- | --- |
| `prepare(path, settings) -> Session` | Checks the extension (`.png`, `.jpg`, `.jpeg`, `.webp`), the size (up to `max_upload_mb`) and that the file opens as an image. Returns a fresh `Session`: RGB image, new token, map size 25 x 25 (`default`), detect option on, no mask, new temp folder. Raises `UploadRejected` otherwise | None |
| `set_map_size(session, width, height)` | Validates 1..200 whole numbers (raises `MapSizeInvalid`). Sets the size with source `typed` and turns the detect option off. Returns the proportions warning, if any | None |
| `set_detect(session, on)` | Turns the detect option on or off | None |
| `can_start(session, kind) -> bool` | `quick`: an image is loaded and nothing is running. `deep`: also a mask is on screen | None |
| `begin_pass(session, kind) -> PassTicket` | Re-checks `can_start` and the map size, marks the pass as running, and returns a ticket: the session token, the kind, the start time, and the map size to trace with (`None` when the detect option is on) | None |
| `finish_pass(session, ticket, outcome) -> bool` | Applies a `TraceResult` or a `PassFailure`. Returns `False` and changes nothing if the ticket's token is no longer the session's (a new upload came in). On success: replaces the mask; if the size was detected and the user has not typed one meanwhile, sets the map size and turns the option off. On failure: records it and keeps the earlier mask. Clears the running mark either way | None |
| `preview(session) -> Image` | The upload, with the mask drawn over it when there is one | None |
| `export(session) -> Path` | Writes the mask on screen to the session's temp folder as `<image name><extension>` and returns the path. Raises if there is no mask | None |
| `status_line(session) -> str` | Model label and effort, time, estimated cost, counts, and the model's note, for the last successful pass. Empty when there is none | None |
| `button_labels(settings) -> dict` | The two pass buttons' labels with expected time and cost from the config | None |
| `close(session)` | Removes the session's temp folder | None |

Guarantees:

- No function here raises anything but `UploadRejected` and `MapSizeInvalid` for user
  input; both carry a ready message.
- `finish_pass` with a failure never clears `session.result`.
- Nothing is written outside the session's temp folder.

## `app/tracer.py`

`run_pass(image, map_size, fallback_size, kind, settings, client=None) -> TraceResult | PassFailure`

- `map_size`: the size to trace with, or `None` to let the model work it out first.
  `fallback_size` is used when no grid is found.
- The only function that calls the model. It never raises: every error and every bad stop
  becomes a `PassFailure` (kinds and causes in [ui.md](ui.md)).
- With no `ANTHROPIC_API_KEY` and no `client` given, it returns `missing_key` without
  making a request.
- Steps: optional `llm.agent.detect_map_size()`; `llm.agent.trace_map()` with the
  profile's config and deadline; validate the last submission; convert to image fractions;
  fill in model, effort, served-by, elapsed time, usage and estimated cost.
- `client` lets tests pass the scripted fake client.

## `app/exporter.py`

`build(result, map_size, image, settings) -> dict` and `write(path, payload)`.
Output defined in [export-file.md](export-file.md).

## `app/render.py`

`overlay(image, result | None) -> Image`: a copy of the image with walls, portals and
lights drawn in three distinct colors, line width scaled to the image; the image alone
when `result` is `None`. Never changes its input.

## `llm/agent.py` (changes)

- `load_config(profile="quick", path=CONFIG) -> dict`: `cfg["model"]` set from the profile.
- `detect_map_size(image, cfg, client, trace) -> tuple[int, int] | None`: one model turn
  with the `report_map_size` tool; adds its usage to `trace`; `None` when no grid is found
  or the size is outside 1..200.
- `trace_map(..., deadline=None, trace=None)`: stops with `stopped = "timeout"` once the
  deadline passes and gives each request the remaining time as its timeout. Keeps each raw
  response's text and tool calls on the `Trace` for the run folder. The tracing logic,
  prompt, tools and views are otherwise unchanged.
