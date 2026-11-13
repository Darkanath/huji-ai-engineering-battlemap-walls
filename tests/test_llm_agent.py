"""The Claude tool loop, driven by a scripted fake client (no network, no cost)."""

import time

import pytest
from PIL import Image

from llm import agent
from llm.agent import Trace, detect_map_size, load_config, quadrant_boxes, trace_map

from conftest import FakeClient, call, reply, text

ANSWER = {
    "walls": [{"points": [{"x": 1, "y": 1}, {"x": 9, "y": 1}]}],
    "arcs": [],
    "portals": [],
    "lights": [{"x": 5, "y": 5, "tier": "small"}],
}
VIEW = {"x0": 0, "y0": 0, "x1": 5, "y1": 5, "overlay": False}


def run(script, **limits):
    """Trace a plain 10 x 10 map with a scripted client; returns the trace and the client."""
    cfg = load_config()
    cfg["limits"].update(limits)
    client = FakeClient(script)
    image = Image.new("RGB", (700, 700), (90, 90, 90))
    return trace_map(image, (10, 10), cfg, client), client


def test_view_then_submit_then_done():
    """A view, a submission and a closing remark give a finished trace with its usage."""
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
    """A view past the limit is answered with an error result, not an image."""
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
    """A model that stops before submitting is asked once to submit."""
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
    """The loop stops at the turn limit with no answer."""
    trace, _ = run([reply(call("view_region", VIEW))] * 5, max_turns=2)
    assert trace.stopped == "turn limit" and trace.turns == 2 and trace.answer is None


def test_quadrants_cover_the_map_and_overlap_in_the_middle():
    """The four opening quarters cover the map and overlap by one square."""
    boxes = quadrant_boxes((25, 25))
    assert boxes[0] == (0, 0, 13, 13) and boxes[3] == (12, 12, 25, 25)
    assert len(boxes) == 4


def test_profiles_pick_the_model_and_effort():
    """The quick profile is Sonnet and the deep one Opus, both at medium effort."""
    quick, deep = load_config("quick"), load_config("deep")
    assert (quick["model"]["name"], quick["model"]["effort"]) == ("claude-sonnet-5-5", "medium")
    assert (deep["model"]["name"], deep["model"]["effort"]) == ("claude-opus-5-5", "medium")


def test_changing_cfg_model_leaves_the_profile_alone():
    """`cfg["model"]` is a copy, so an override (llm.run --model) does not edit the profile."""
    cfg = load_config("quick")
    cfg["model"]["name"] = "claude-haiku-5-5"
    assert cfg["profiles"]["quick"]["name"] == "claude-sonnet-5-5"


def test_deadline_already_passed_makes_no_request():
    """With the deadline behind us, the loop stops before its first request."""
    client = FakeClient([])
    image = Image.new("RGB", (700, 700), (90, 90, 90))
    trace = trace_map(image, (10, 10), load_config(), client, deadline=time.monotonic() - 1)
    assert trace.stopped == "timeout" and client.requests == []


def test_deadline_passing_mid_pass_stops_before_the_next_request(monkeypatch):
    """A deadline that passes during the first response stops the loop before the second."""
    clock = iter([100.0, 200.0])  # first check: time left; second check: past the deadline
    monkeypatch.setattr(agent.time, "monotonic", lambda: next(clock))
    client = FakeClient([reply(call("view_region", VIEW)), reply(call("view_region", VIEW))])
    image = Image.new("RGB", (700, 700), (90, 90, 90))
    trace = trace_map(image, (10, 10), load_config(), client, deadline=150.0)
    assert trace.stopped == "timeout" and len(client.requests) == 1
    assert client.requests[0]["timeout"] == 50.0


def test_requests_carry_a_timeout_no_larger_than_the_time_left():
    """Each request's timeout fits inside the deadline."""
    deadline = time.monotonic() + 30
    client = FakeClient([reply(call("submit_answer", ANSWER)), reply(text("ok"), stop="end_turn")])
    image = Image.new("RGB", (700, 700), (90, 90, 90))
    trace_map(image, (10, 10), load_config(), client, deadline=deadline)
    assert all(0 < r["timeout"] <= 30 for r in client.requests)


def test_raw_responses_are_kept_on_the_trace():
    """Each response's text and tool calls are recorded, in the fixture format."""
    trace, _ = run([reply(call("submit_answer", ANSWER)), reply(text("Done."), stop="end_turn")])
    assert trace.responses == [
        {
            "stop_reason": "tool_use",
            "model": "fake-model",
            "content": [{"type": "tool_use", "name": "submit_answer", "input": ANSWER, "id": "t1"}],
        },
        {
            "stop_reason": "end_turn",
            "model": "fake-model",
            "content": [{"type": "text", "text": "Done."}],
        },
    ]


def size_reply(**args):
    """A reply calling report_map_size with the given arguments."""
    return reply(call("report_map_size", args))


def detect(script):
    """Run the map-size step on a plain 700 x 800 image; returns size, trace and client."""
    client, trace = FakeClient(script), Trace()
    image = Image.new("RGB", (700, 800), (90, 90, 90))
    return detect_map_size(image, load_config(), client, trace), trace, client


def test_detect_map_size_offers_only_the_size_tool_and_reads_the_answer():
    """One request, only report_map_size offered; a found grid gives its size and usage."""
    size, trace, client = detect([size_reply(grid_found=True, width=26, height=28)])
    assert size == (26, 28)
    assert len(client.requests) == 1
    assert [t["name"] for t in client.requests[0]["tools"]] == ["report_map_size"]
    assert trace.input_tokens == 1000 and trace.cost_usd > 0


def test_detect_map_size_no_grid_returns_none():
    """grid_found false means no size."""
    assert detect([size_reply(grid_found=False, width=0, height=0)])[0] is None


@pytest.mark.parametrize("bad", [0, 201])
def test_detect_map_size_out_of_range_returns_none(bad):
    """A size outside 1..200 is not used."""
    assert detect([size_reply(grid_found=True, width=bad, height=10)])[0] is None


def test_detect_map_size_without_a_tool_call_returns_none():
    """A text-only reply gives no size."""
    assert detect([reply(text("I can't tell."), stop="end_turn")])[0] is None


def test_cost_is_added_per_response_at_each_models_price():
    """Two responses at two prices cost the sum of each at its own price."""
    trace = Trace()
    usage = reply().usage
    trace.add_usage(usage, {"input": 4.0, "output": 20.0})
    trace.add_usage(usage, {"input": 2.0, "output": 10.0})
    assert trace.cost_usd == pytest.approx((1000 * 4 + 100 * 20 + 1000 * 2 + 100 * 10) / 1e6)
    assert trace.input_tokens == 2000


def test_detect_map_size_uses_the_configs_limits():
    """A size inside 1..200 but above [app] max_squares is not used."""
    client, trace = FakeClient([size_reply(grid_found=True, width=150, height=10)]), Trace()
    cfg = load_config()
    cfg["app"]["max_squares"] = 100
    image = Image.new("RGB", (700, 800), (90, 90, 90))
    assert detect_map_size(image, cfg, client, trace) is None
