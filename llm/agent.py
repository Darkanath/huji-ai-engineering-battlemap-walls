"""The Claude wall tracer: a tool loop that reads a battlemap and returns its walls.

Claude gets the whole map with a labeled grid, asks for zoomed crops (`view_region`) and submits
walls, portals and lights in grid squares (`submit_answer`). Each submission comes back drawn
over the map so the model can check and correct it. The last submission is the result.

A spike on 13.11 (docs/results.md) showed why the loop is needed: one look at the full image is
enough to understand the layout, but not to place doors and wall ends within 0.1 square.
"""

import tomllib
from dataclasses import dataclass, field
from pathlib import Path

import anthropic
from PIL import Image

from llm.views import render_view, to_image_block
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


def load_config(path: Path = CONFIG) -> dict:
    """Read the tracer settings (model, limits, view sizes, prices)."""
    return tomllib.loads(path.read_text())


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

    def add_usage(self, usage, prices: dict) -> None:
        """Add one response's token counts and update the cost estimate."""
        self.input_tokens += usage.input_tokens or 0
        self.output_tokens += usage.output_tokens or 0
        self.cache_write_tokens += getattr(usage, "cache_creation_input_tokens", 0) or 0
        self.cache_read_tokens += getattr(usage, "cache_read_input_tokens", 0) or 0
        weighted_in = (
            self.input_tokens
            + CACHE_WRITE * self.cache_write_tokens
            + CACHE_READ * self.cache_read_tokens
        )
        self.cost_usd = (
            weighted_in * prices["input"] + self.output_tokens * prices["output"]
        ) / 1e6


def _request(client: anthropic.Anthropic, cfg: dict, messages: list[dict]):
    """One Messages API call with the tracer's fixed settings."""
    model = cfg["model"]
    params = {
        "model": model["name"],
        "max_tokens": model["max_tokens"],
        "system": SYSTEM,
        "tools": TOOLS,
        "messages": messages,
        "thinking": {"type": "adaptive"},
        "output_config": {"effort": model["effort"]},
        "cache_control": {"type": "ephemeral"},  # each turn re-reads the earlier turns cheaply
    }
    if model.get("fallbacks") and not model["name"].startswith("claude-haiku"):
        return client.beta.messages.create(betas=[FALLBACK_BETA], fallbacks="default", **params)
    return client.messages.create(**params)


def trace_map(
    image: Image.Image,
    map_size: tuple[int, int],
    cfg: dict | None = None,
    client: anthropic.Anthropic | None = None,
    views_dir: Path | None = None,
) -> Trace:
    """Run the tool loop on one map image and return the answer with its usage.

    `map_size` is the map's width and height in grid squares. With `views_dir`, every image
    sent to the model is also saved there, for inspection and for the presentation.
    """
    cfg = cfg or load_config()
    client = client or anthropic.Anthropic()
    limits, view_cfg = cfg["limits"], cfg["views"]
    prices = cfg["prices"][cfg["model"]["name"]]
    ppg = image.width / map_size[0]
    trace = Trace()
    uvtt: dict | None = None  # the latest submission, for overlays
    shots = 0

    def show(box, with_overlay: bool) -> tuple[dict, float]:
        """Render a window, save a copy if asked, and return it as an image block."""
        nonlocal shots
        view, zoom = render_view(
            image,
            ppg,
            box,
            view_cfg["max_px"],
            view_cfg["max_zoom"],
            uvtt if with_overlay else None,
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
            block, zoom = show((args["x0"], args["y0"], args["x1"], args["y1"]), args["overlay"])
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
            block, _ = show((0, 0, *map_size), True)
            left = limits["max_submissions"] - trace.submissions
            text = (
                f"Recorded: {len(uvtt['line_of_sight'])} wall lines, {len(uvtt['portals'])} "
                f"portals, {len(uvtt['lights'])} lights. This is your answer drawn over the "
                f"map. Submissions left: {left}."
            )
            return [block, {"type": "text", "text": text}], False
        return [{"type": "text", "text": f"Unknown tool {name}."}], True

    # The opening message: the whole map, then four overlapping quarters at higher zoom, so
    # close reading does not depend on the model asking for it (v1 models rarely asked).
    content: list[dict] = [{"type": "text", "text": "The whole map:"}]
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
        response = _request(client, cfg, messages)
        trace.turns += 1
        trace.add_usage(response.usage, prices)
        trace.served_by.add(response.model)
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
