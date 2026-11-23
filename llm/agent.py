"""The Claude wall tracer: a tool loop that reads a battlemap and returns its walls.

Claude gets the whole map with a labeled grid, asks for zoomed crops (`view_region`) and submits
walls, portals and lights in grid squares (`submit_answer`). Each submission comes back drawn
over the map so the model can check and correct it. The last submission is the result.

A spike on 13.11 (docs/results.md) showed why the loop is needed: one look at the full image is
enough to understand the layout, but not to place doors and wall ends within 0.1 square.
"""

import time
import tomllib
from dataclasses import dataclass, field
from pathlib import Path

import anthropic
from PIL import Image

from llm.views import Box, render_view, to_image_block
from postprocess.uvtt import answer_to_uvtt

CONFIG = Path(__file__).parent / "configs" / "claude.toml"
FALLBACK_BETA = "server-side-fallback-2026-07-01"
CACHE_WRITE, CACHE_READ = 1.25, 0.1  # cost of cached input tokens, relative to normal input

SYSTEM = """\
You trace battlemaps for virtual tabletops. Given a top-down map image, you return its walls, \
portals and light sources as coordinates, which become line-of-sight data for dynamic lighting \
and fog of war in Roll20. A wall that is missing, or a gap that should not be there, lets \
players see into rooms they have not entered, so completeness and position both matter.

## Coordinates
All coordinates are in grid squares, as decimals. The origin is the map's top-left corner, x \
grows to the right and y grows down. Every image you receive has the square numbers in its top \
and left margins, short ticks every half square, and thin grid lines on whole squares (cyan \
for x, magenta for y). Read positions off those; aim for an error under 0.1 square.

## What to mark
- Wall: anything that blocks both sight and movement: building walls, palisades, cave walls, \
cliff faces. Trace the centerline of the drawn wall. For caves, follow the middle of the rock \
border between floor and solid rock, with a point about every square, closer on tight bends.
- Portal: a door or a window in a wall, as one segment from end to end. The wall must stop at \
both ends of the portal: do not draw a wall through it. An open gap or archway with no door \
drawn in it is just a gap: no wall and no portal there.
- Light: a lit light source drawn in the image, at its center. Tier "small" for a candle, \
torch or wall sconce; "medium" for a lantern, brazier, campfire or fireplace; "large" for a \
bonfire, large fire pit or forge. Unlit fixtures and glow without a visible source are not \
lights.
- Not walls: furniture, counters, rugs, stages, crates, trees, boulders, water, fences and \
railings low enough to see over, floor patterns, rails, and the map's own border.

Many buildings sit on the grid, so wall centerlines often fall on whole or half squares; use \
that when the image supports it, and do not force it when it does not. Round rooms and towers \
are best given as arcs. Walls that meet should share the same end point.

## How to work
You first get the whole map, then its four quarters at higher zoom (they overlap by one \
square). The whole map is for understanding the layout; read positions from the quarters. \
They are still too coarse for small things: use view_region for a closer crop wherever a door, \
a window, a wall end or a light needs it, and along every wall that might hold doors or \
windows. You can ask for several regions in one turn. Then call submit_answer with the \
complete answer. It returns your answer drawn over the \
map; compare it with the drawing, look closer at anything doubtful with view_region \
(overlay=true shows your lines on the crop), and submit a corrected, complete answer if needed. \
The last submission is the result. When it is right, reply with one short sentence saying so, \
plus anything you were unsure about.

View and submission counts are limited, so plan them: a handful of views that cover the \
structure, rather than many tiny ones."""

# A chunk agent (specs/002-chunked-map-tracing/) gets the same role, coordinates and labeling
# rules word for word; only "How to work" differs. SYSTEM itself is left exactly as it was, so
# the single-session passes send what they always sent (tests/fixtures/request_single_session.json).
CHUNK_SYSTEM = (
    SYSTEM.split("## How to work")[0]
    + """## How to work
You trace one part of a larger map. Other agents trace the other parts at the same time, and \
their answers are joined afterwards, so stay inside your part. All coordinates are the whole \
map's: read them off the labels, as on any view. You first get the whole map with your part \
outlined in green, so you know what continues past your edges, then your part at higher zoom. \
Trace everything inside your part up to its edge: a wall that runs on into a neighbour's part \
stops exactly at your edge. Your part includes a margin that a neighbouring agent also traces; \
trace it too, so the joins can be checked. Do not trace anything outside your part. Use \
view_region for closer crops wherever a door, a window, a wall end or a light needs it, and \
along every wall that might hold doors or windows. Then call submit_answer with the complete \
answer for your part. It returns your answer drawn over your part; compare it with the \
drawing, look closer at anything doubtful with view_region (overlay=true shows your lines on \
the crop), and submit a corrected, complete answer if needed. The last submission is the \
result. When it is right, reply with one short sentence saying so, plus anything you were \
unsure about.

View and submission counts are limited, so plan them: a handful of views that cover your \
part, rather than many tiny ones."""
)

POINT = {
    "type": "object",
    "properties": {"x": {"type": "number"}, "y": {"type": "number"}},
    "required": ["x", "y"],
    "additionalProperties": False,
}


def _obj(properties: dict) -> dict:
    """A strict JSON-schema object: every property required, nothing extra allowed."""
    return {
        "type": "object",
        "properties": properties,
        "required": list(properties),
        "additionalProperties": False,
    }


NUM = {"type": "number"}
TOOLS = [
    {
        "name": "view_region",
        "description": (
            "Return a zoomed crop of the map with the labeled grid. Give the window in grid "
            "squares. Smaller windows are shown at higher zoom; a window 6 to 10 squares wide "
            "is usually sharp enough to place doors. Set overlay to true to draw your latest "
            "submitted answer on the crop."
        ),
        "strict": True,
        "input_schema": _obj(
            {"x0": NUM, "y0": NUM, "x1": NUM, "y1": NUM, "overlay": {"type": "boolean"}}
        ),
    },
    {
        "name": "submit_answer",
        "description": (
            "Submit the complete answer for the whole map (it replaces any earlier submission) "
            "and get it back drawn over the map: walls red, portals magenta, lights yellow. "
            "Arc angles are in degrees, measured at the center from the +x direction (east) "
            "toward +y (south), so east is 0, south 90, west 180 and north 270; an arc runs "
            "from start_deg to end_deg, and end_deg may exceed 360."
        ),
        "strict": True,
        "input_schema": _obj(
            {
                "walls": {
                    "type": "array",
                    "description": "Polylines along wall centerlines.",
                    "items": _obj({"points": {"type": "array", "items": POINT}}),
                },
                "arcs": {
                    "type": "array",
                    "description": "Circular wall pieces, for round rooms and towers.",
                    "items": _obj(
                        {"cx": NUM, "cy": NUM, "r": NUM, "start_deg": NUM, "end_deg": NUM}
                    ),
                },
                "portals": {
                    "type": "array",
                    "description": "Doors and windows, each as a segment between its two ends.",
                    "items": _obj({"x1": NUM, "y1": NUM, "x2": NUM, "y2": NUM}),
                },
                "lights": {
                    "type": "array",
                    "items": _obj(
                        {
                            "x": NUM,
                            "y": NUM,
                            "tier": {"type": "string", "enum": ["small", "medium", "large"]},
                        }
                    ),
                },
            }
        ),
    },
]


def quadrant_boxes(map_size: tuple[int, int], overlap: float = 1.0) -> list[tuple]:
    """Four windows covering the map, 2 x 2, each reaching `overlap` squares past the middle."""
    w, h = map_size
    xs = [(0, w / 2 + overlap / 2), (w / 2 - overlap / 2, w)]
    ys = [(0, h / 2 + overlap / 2), (h / 2 - overlap / 2, h)]
    return [(x0, y0, x1, y1) for y0, y1 in ys for x0, x1 in xs]


def size_step_config(path: Path = CONFIG) -> dict:
    """The config for the map-size step: the profile named in `[size_step]`, in either pass."""
    profile = tomllib.loads(path.read_text())["size_step"]["profile"]
    return load_config(profile, path)


def load_config(profile: str = "quick", path: Path = CONFIG) -> dict:
    """Read the tracer settings (limits, view sizes, prices) for one model profile.

    `profile` names a `[profiles.*]` table ("quick" or "deep"); a copy of it becomes
    `cfg["model"]`, which is what the tool loop reads, so changing it never touches the profile.
    """
    cfg = tomllib.loads(path.read_text())
    if profile not in cfg["profiles"]:
        raise ValueError(f"unknown profile {profile!r}; expected one of {sorted(cfg['profiles'])}")
    cfg["model"] = dict(cfg["profiles"][profile])
    return cfg


@dataclass
class Trace:
    """What one map cost and produced."""

    answer: dict | None = None  # the last submission, None if the model never submitted
    turns: int = 0
    views: int = 0
    submissions: int = 0
    input_tokens: int = 0
    output_tokens: int = 0
    cache_write_tokens: int = 0
    cache_read_tokens: int = 0
    cost_usd: float = 0.0
    served_by: set[str] = field(default_factory=set)  # models that answered (fallbacks show here)
    stopped: str = ""  # why the loop ended
    note: str = ""  # the model's closing remark
    log: list[dict] = field(default_factory=list)  # one entry per tool call, for the run folder
    # Each raw response's text and tool calls (no thinking, no images), for the run folder and
    # for recording test fixtures.
    responses: list[dict] = field(default_factory=list)

    def add_usage(self, usage, prices: dict) -> None:
        """Add one response's token counts and its cost at `prices` to the running totals.

        Cost is added per response, so a pass that uses two models (the map-size step on one,
        the trace on another) is priced correctly.
        """
        inp = usage.input_tokens or 0
        out = usage.output_tokens or 0
        cache_write = getattr(usage, "cache_creation_input_tokens", 0) or 0
        cache_read = getattr(usage, "cache_read_input_tokens", 0) or 0
        self.input_tokens += inp
        self.output_tokens += out
        self.cache_write_tokens += cache_write
        self.cache_read_tokens += cache_read
        weighted_in = inp + CACHE_WRITE * cache_write + CACHE_READ * cache_read
        self.cost_usd += (weighted_in * prices["input"] + out * prices["output"]) / 1e6

    def record(self, response) -> None:
        """Keep a response's text and tool-call blocks, in the fixture format of tests/."""
        blocks = []
        for b in response.content:
            if b.type == "text":
                blocks.append({"type": "text", "text": b.text})
            elif b.type == "tool_use":
                blocks.append({"type": "tool_use", "name": b.name, "input": b.input, "id": b.id})
        self.responses.append(
            {"stop_reason": response.stop_reason, "model": response.model, "content": blocks}
        )


def _time_left(deadline: float | None) -> float | None:
    """Seconds until `deadline` (a time.monotonic() value), or None when there is none."""
    return None if deadline is None else deadline - time.monotonic()


def _request(
    client: anthropic.Anthropic,
    cfg: dict,
    messages: list[dict],
    timeout: float | None = None,
    system: str = SYSTEM,
    tools: list[dict] = TOOLS,
):
    """One Messages API call with the tracer's fixed settings.

    `timeout` (seconds) bounds this request; `system` and `tools` default to the tracing ones.
    """
    model = cfg["model"]
    params = {
        "model": model["name"],
        "max_tokens": model["max_tokens"],
        "system": system,
        "tools": tools,
        "messages": messages,
        "thinking": {"type": "adaptive"},
        "output_config": {"effort": model["effort"]},
        "cache_control": {"type": "ephemeral"},  # each turn re-reads the earlier turns cheaply
    }
    if timeout is not None:
        params["timeout"] = timeout
    if model.get("fallbacks") and not model["name"].startswith("claude-haiku"):
        return client.beta.messages.create(betas=[FALLBACK_BETA], fallbacks="default", **params)
    return client.messages.create(**params)


def trace_map(
    image: Image.Image,
    map_size: tuple[int, int],
    cfg: dict | None = None,
    client: anthropic.Anthropic | None = None,
    views_dir: Path | None = None,
    deadline: float | None = None,
    trace: Trace | None = None,
    window: Box | None = None,
    core: Box | None = None,
) -> Trace:
    """Run the tool loop on one map image and return the answer with its usage.

    `map_size` is the map's width and height in grid squares. With `views_dir`, every image
    sent to the model is also saved there, for inspection and for the presentation.
    `deadline` is a time.monotonic() value: no request starts after it (the loop stops with
    `stopped = "timeout"`), and each request may take only the time left. Pass a `trace` to
    add to one that already holds usage (the map-size step); if a request raises, that trace
    still holds everything spent before it.

    With `window` (a box in whole-map squares) the loop runs as one chunk agent of the chunked
    pass: `CHUNK_SYSTEM`, the whole map with the window outlined, then the window itself, crops
    clamped to the window, and the answer overlay drawn on the window. `core` is the chunk's
    own area inside the window, named in the intro (default: the window). Answers stay in
    whole-map squares. Without `window`, nothing differs from before the chunked pass existed.
    """
    cfg = cfg or load_config()
    client = client or anthropic.Anthropic()
    limits, view_cfg = cfg["limits"], cfg["views"]
    prices = cfg["prices"][cfg["model"]["name"]]
    ppg = image.width / map_size[0]
    trace = trace if trace is not None else Trace()
    uvtt: dict | None = None  # the latest submission, for overlays
    shots = 0

    def show(box, with_overlay: bool, outline: Box | None = None) -> tuple[dict, float]:
        """Render a window, save a copy if asked, and return it as an image block."""
        nonlocal shots
        view, zoom = render_view(
            image,
            ppg,
            box,
            view_cfg["max_px"],
            view_cfg["max_zoom"],
            uvtt if with_overlay else None,
            outline=outline,
        )
        if views_dir is not None:
            views_dir.mkdir(parents=True, exist_ok=True)
            view.save(views_dir / f"{shots:02d}.jpg", quality=view_cfg["jpeg_quality"])
        shots += 1
        return to_image_block(view, view_cfg["jpeg_quality"]), zoom

    def run_tool(name: str, args: dict) -> tuple[list[dict], bool]:
        """Execute one tool call; returns the result content and whether it is an error."""
        nonlocal uvtt
        if name == "view_region":
            if trace.views >= limits["max_views"]:
                return [{"type": "text", "text": "View limit reached. Submit your answer."}], True
            if args["overlay"] and uvtt is None:
                return [{"type": "text", "text": "Nothing submitted yet: no overlay."}], True
            trace.views += 1
            box = (args["x0"], args["y0"], args["x1"], args["y1"])
            if window is not None:
                box = _within(box, window)
            block, zoom = show(box, args["overlay"])
            left = limits["max_views"] - trace.views
            text = f"{zoom:.0f} px per square. Views left: {left}."
            return [block, {"type": "text", "text": text}], False
        if name == "submit_answer":
            if trace.submissions >= limits["max_submissions"]:
                text = "Submission limit reached; the previous submission stands. Finish now."
                return [{"type": "text", "text": text}], True
            trace.submissions += 1
            trace.answer = args
            uvtt = answer_to_uvtt(args, map_size)
            block, _ = show(window or (0, 0, *map_size), True)
            left = limits["max_submissions"] - trace.submissions
            text = (
                f"Recorded: {len(uvtt['line_of_sight'])} wall lines, {len(uvtt['portals'])} "
                f"portals, {len(uvtt['lights'])} lights. This is your answer drawn over the "
                f"map. Submissions left: {left}."
            )
            return [block, {"type": "text", "text": text}], False
        return [{"type": "text", "text": f"Unknown tool {name}."}], True

    if window is not None:
        content = _chunk_opening(show, map_size, window, core or window)
    else:
        # The opening message: the whole map, then four overlapping quarters at higher zoom, so
        # close reading does not depend on the model asking for it (v1 models rarely asked).
        content = [{"type": "text", "text": "The whole map:"}]
        content.append(show((0, 0, *map_size), False)[0])
        if view_cfg.get("quadrants", True):
            for box in quadrant_boxes(map_size):
                label = f"Squares x {box[0]:g} to {box[2]:g}, y {box[1]:g} to {box[3]:g}:"
                content += [{"type": "text", "text": label}, show(box, False)[0]]
        intro = f"Trace this map. It is {map_size[0]} squares wide and {map_size[1]} squares high."
        content.append({"type": "text", "text": intro})
    messages: list[dict] = [{"role": "user", "content": content}]
    reminded = False

    while True:
        if trace.turns >= limits["max_turns"]:
            trace.stopped = "turn limit"
            break
        if trace.cost_usd >= limits["max_cost_usd"]:
            trace.stopped = "cost limit"
            break
        left = _time_left(deadline)
        if left is not None and left <= 0:
            trace.stopped = "timeout"
            break
        response = _request(
            client, cfg, messages, timeout=left, system=SYSTEM if window is None else CHUNK_SYSTEM
        )
        trace.turns += 1
        trace.add_usage(response.usage, prices)
        trace.served_by.add(response.model)
        trace.record(response)
        messages.append({"role": "assistant", "content": response.content})

        if response.stop_reason in ("refusal", "max_tokens"):
            trace.stopped = response.stop_reason
            break
        calls = [b for b in response.content if b.type == "tool_use"]
        if not calls:
            text = " ".join(b.text for b in response.content if b.type == "text").strip()
            if trace.answer is None and not reminded:
                # tool_choice cannot force a call on current models, so ask once more.
                reminded = True
                nudge = "You have not called submit_answer yet. Submit your answer with it."
                messages.append({"role": "user", "content": nudge})
                continue
            trace.note, trace.stopped = text, "done"
            break

        results = []
        for call in calls:
            content, is_error = run_tool(call.name, call.input)
            trace.log.append(
                {"turn": trace.turns, "tool": call.name, "input": call.input, "error": is_error}
            )
            results.append(
                {
                    "type": "tool_result",
                    "tool_use_id": call.id,
                    "content": content,
                    "is_error": is_error,
                }
            )
        messages.append({"role": "user", "content": results})
    return trace


def _within(box: Box, window: Box) -> Box:
    """`box` cut down to `window`; the whole window when they do not overlap."""
    x0, y0 = max(min(box[0], box[2]), window[0]), max(min(box[1], box[3]), window[1])
    x1, y1 = min(max(box[0], box[2]), window[2]), min(max(box[1], box[3]), window[3])
    return (x0, y0, x1, y1) if x0 < x1 and y0 < y1 else window


def _span(box: Box) -> str:
    """ "x 0 to 13.5, y 0 to 13.5" for a box in squares."""
    return f"x {box[0]:g} to {box[2]:g}, y {box[1]:g} to {box[3]:g}"


def chunk_intro(map_size: tuple[int, int], window: Box, core: Box) -> str:
    """A chunk agent's instructions for its part (the orchestrator's routing tests read it)."""
    return (
        f"Trace your part of this map. The map is {map_size[0]} squares wide and "
        f"{map_size[1]} squares high. Your part is {_span(window)}. Its own area is "
        f"{_span(core)}; the rest of your part is a margin that a neighbouring agent also "
        "traces, so trace it too, up to the edge of your part."
    )


def _chunk_opening(show, map_size: tuple[int, int], window: Box, core: Box) -> list[dict]:
    """A chunk agent's first message: the outlined overview, its window, and the intro."""
    return [
        {"type": "text", "text": "The whole map, your part outlined in green:"},
        show((0, 0, *map_size), False, outline=window)[0],
        {"type": "text", "text": f"Your part, {_span(window)}:"},
        show(window, False)[0],
        {"type": "text", "text": chunk_intro(map_size, window, core)},
    ]


SIZE_SYSTEM = """\
You measure battlemaps for virtual tabletops. Given a top-down map image, count its grid \
squares: how many whole squares across (width) and down (height). Only square grids count. \
You get the whole map, then its top and left edges at higher zoom, where the grid lines are \
easiest to count. Answer with report_map_size. Set grid_found to false when the map has no \
visible square grid, or when its squares cannot be counted with confidence; then give 0 for \
width and height."""

SIZE_TOOL = {
    "name": "report_map_size",
    "description": "Report the map's size in grid squares, or that no grid was found.",
    "strict": True,
    "input_schema": _obj(
        {
            "grid_found": {"type": "boolean"},
            "width": {"type": "integer"},
            "height": {"type": "integer"},
        }
    ),
}
SIZE_RANGE = (1, 200)  # squares per side, unless the config's [app] table narrows it
EDGE_SHARE = 0.12  # each edge strip is this share of the map's height (top) or width (left)


def _fit(image: Image.Image, max_px: int) -> Image.Image:
    """The image scaled down so its longer side is at most `max_px` (never up)."""
    scale = min(1.0, max_px / max(image.size))
    if scale == 1.0:
        return image
    return image.resize((round(image.width * scale), round(image.height * scale)), Image.LANCZOS)


def size_views(image: Image.Image, max_px: int) -> list[tuple[str, Image.Image]]:
    """The map-size step's images: the whole map, then each half of the top and left edges.

    Halving each edge strip doubles its zoom compared with the whole map. No grid overlay is
    drawn: the model counts the map's own grid.
    """
    w, h = image.size
    top, left = max(1, round(h * EDGE_SHARE)), max(1, round(w * EDGE_SHARE))
    crops = [
        ("Top edge, left half:", (0, 0, w // 2, top)),
        ("Top edge, right half:", (w // 2, 0, w, top)),
        ("Left edge, upper half:", (0, 0, left, h // 2)),
        ("Left edge, lower half:", (0, h // 2, left, h)),
    ]
    out = [("The whole map:", _fit(image, max_px))]
    out += [(label, _fit(image.crop(box), max_px)) for label, box in crops]
    return out


def detect_map_size(
    image: Image.Image,
    cfg: dict,
    client: anthropic.Anthropic,
    trace: Trace,
    deadline: float | None = None,
) -> tuple[int, int] | None:
    """Ask the model, in one request, how many grid squares the map has across and down.

    Uses the model in `cfg["model"]` (the app passes the `[size_step]` profile, Opus, in both
    passes); the response's usage and cost are added to `trace`, so the pass reports one total.
    Returns (width, height), or None when no grid was found, the model gave no size, or the
    size is outside 1..200. A refusal sets `trace.stopped = "refusal"`; a
    deadline already passed sets it to "timeout". API errors are raised to the caller.
    """
    left = _time_left(deadline)
    if left is not None and left <= 0:
        trace.stopped = "timeout"
        return None
    view_cfg = cfg["views"]
    content: list[dict] = []
    for label, view in size_views(image, view_cfg["max_px"]):
        content += [{"type": "text", "text": label}, to_image_block(view, view_cfg["jpeg_quality"])]
    content.append({"type": "text", "text": "How many grid squares is this map across and down?"})
    messages = [{"role": "user", "content": content}]
    response = _request(client, cfg, messages, timeout=left, system=SIZE_SYSTEM, tools=[SIZE_TOOL])
    trace.add_usage(response.usage, cfg["prices"][cfg["model"]["name"]])
    trace.served_by.add(response.model)
    trace.record(response)
    if response.stop_reason == "refusal":
        trace.stopped = "refusal"
        return None
    for block in response.content:
        if block.type == "tool_use" and block.name == "report_map_size":
            args = block.input
            if not args.get("grid_found"):
                return None
            size = args.get("width"), args.get("height")
            app = cfg.get("app", {})
            low = app.get("min_squares", SIZE_RANGE[0])
            high = app.get("max_squares", SIZE_RANGE[1])
            if all(isinstance(v, int) and low <= v <= high for v in size):
                return size
            return None
    return None
