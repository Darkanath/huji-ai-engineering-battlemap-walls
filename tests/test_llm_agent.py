"""The Claude tool loop, driven by a scripted fake client (no network, no cost)."""

from types import SimpleNamespace as NS

from PIL import Image

from llm.agent import load_config, quadrant_boxes, trace_map

ANSWER = {
    "walls": [{"points": [{"x": 1, "y": 1}, {"x": 9, "y": 1}]}],
    "arcs": [],
    "portals": [],
    "lights": [{"x": 5, "y": 5, "tier": "small"}],
}
VIEW = {"x0": 0, "y0": 0, "x1": 5, "y1": 5, "overlay": False}


def reply(*blocks, stop="tool_use"):
    """A fake API response with 1,000 input and 100 output tokens."""
    usage = NS(
        input_tokens=1000,
        output_tokens=100,
        cache_creation_input_tokens=0,
        cache_read_input_tokens=0,
    )
    return NS(content=list(blocks), stop_reason=stop, usage=usage, model="fake-model")


def call(name, args, id_="t1"):
    return NS(type="tool_use", name=name, input=args, id=id_)


def text(body):
    return NS(type="text", text=body)


class FakeClient:
    """Returns the scripted responses in order and records every request."""

    def __init__(self, script):
        self.script, self.requests = list(script), []
        self.messages = self
        self.beta = NS(messages=self)

    def create(self, **params):
        self.requests.append({**params, "messages": list(params["messages"])})
        return self.script.pop(0)


def run(script, **limits):
    cfg = load_config()
    cfg["limits"].update(limits)
    client = FakeClient(script)
    image = Image.new("RGB", (700, 700), (90, 90, 90))
    return trace_map(image, (10, 10), cfg, client), client


def test_view_then_submit_then_done():
    trace, client = run(
        [
            reply(call("view_region", VIEW)),
            reply(call("submit_answer", ANSWER)),
            reply(text("Done."), stop="end_turn"),
        ]
    )
    assert trace.stopped == "done" and trace.note == "Done."
    assert trace.answer == ANSWER
    assert (trace.turns, trace.views, trace.submissions) == (3, 1, 1)
    assert trace.input_tokens == 3000 and trace.cost_usd > 0
    # The first request carries the overview image; tool results come back as image + text.
    first = client.requests[0]["messages"][0]["content"]
    assert [b["type"] for b in first].count("image") == 5  # the overview and four quarters
    assert first[-1]["type"] == "text"
    result = client.requests[1]["messages"][-1]["content"][0]
    assert result["type"] == "tool_result" and result["tool_use_id"] == "t1"
    assert [b["type"] for b in result["content"]] == ["image", "text"]


def test_view_limit_returns_an_error_result():
    trace, client = run(
        [
            reply(call("view_region", VIEW), call("view_region", VIEW, "t2")),
            reply(call("submit_answer", ANSWER)),
            reply(text("ok"), stop="end_turn"),
        ],
        max_views=1,
    )
    results = client.requests[1]["messages"][-1]["content"]
    assert [r["is_error"] for r in results] == [False, True]
    assert trace.views == 1


def test_model_is_reminded_once_when_it_stops_without_submitting():
    trace, client = run(
        [
            reply(text("I looked at it."), stop="end_turn"),
            reply(call("submit_answer", ANSWER)),
            reply(text("ok"), stop="end_turn"),
        ]
    )
    assert trace.answer == ANSWER
    assert "submit_answer" in client.requests[1]["messages"][-1]["content"]


def test_turn_limit_stops_the_loop():
    trace, _ = run([reply(call("view_region", VIEW))] * 5, max_turns=2)
    assert trace.stopped == "turn limit" and trace.turns == 2 and trace.answer is None


def test_quadrants_cover_the_map_and_overlap_in_the_middle():
    boxes = quadrant_boxes((25, 25))
    assert boxes[0] == (0, 0, 13, 13) and boxes[3] == (12, 12, 25, 25)
    assert len(boxes) == 4
