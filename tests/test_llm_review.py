"""The orchestrator model's seam review (`llm/review.py`), with a scripted fake client."""

import json
import time

import anthropic
import httpx2
from PIL import Image

from llm.merge import chunk_layout, seams
from llm.orchestrator import load_chunked_config
from llm.review import REVIEW_SYSTEM, ReviewState, review_seams

from conftest import FakeClient, call, reply, text

MERGED = {
    "walls": [{"points": [{"x": 3, "y": 5}, {"x": 22, "y": 5}]}],
    "portals": [{"x1": 12, "y1": 5, "x2": 13, "y2": 5}],
    "lights": [{"x": 20, "y": 20, "tier": "small"}],
}
FIX = {
    "walls": [{"points": [{"x": 11.5, "y": 5}, {"x": 13.5, "y": 5}]}],
    "arcs": [],
    "portals": [],
    "lights": [],
}


def run(script, size=(25, 25), deadline=None, **limits):
    """Review a plain 25 x 25 map's two seams with a scripted client."""
    cfg = load_chunked_config("sonnet")
    cfg["review"].update(limits)
    client = FakeClient(script)
    image = Image.new("RGB", (size[0] * 70, size[1] * 70), (90, 90, 90))
    found = seams(chunk_layout(size, 13, 1, 4), size, cfg["review"]["strip_squares"])
    return review_seams(image, size, MERGED, found, cfg, client, deadline=deadline), client


def api_error() -> anthropic.APIConnectionError:
    """A network failure as the SDK raises it."""
    return anthropic.APIConnectionError(request=httpx2.Request("POST", "https://x"))


def test_review_opens_with_strip_crops_and_a_listing_and_applies_nothing_itself():
    """The orchestrator model gets REVIEW_SYSTEM, crops of about 8 squares along each strip
    with the merged lines drawn, and a JSON listing of what lies in the strips."""
    run_, client = run([reply(call("submit_corrections", FIX)), reply(text("ok"), stop="end_turn")])
    first = client.requests[0]
    assert first["system"] == REVIEW_SYSTEM
    assert first["model"] == "claude-sonnet-5-5"
    assert [t["name"] for t in first["tools"]] == ["view_region", "submit_corrections"]
    content = first["messages"][0]["content"]
    assert [b["type"] for b in content].count("image") == 8  # 2 seams x 4 pieces of 6.25
    listing = json.loads(content[-2]["text"])
    assert listing["portals"] == MERGED["portals"]  # its midpoint (12.5, 5) is in a strip
    assert listing["lights"] == []  # (20, 20) is not
    assert len(listing["walls"]) == 1  # the wall's part inside the x = 12.5 strip
    assert run_.state == ReviewState.done and run_.trace.answer == FIX
    assert run_.model == "claude-sonnet-5-5" and run_.removed == {} and run_.added == {}


def test_review_crops_stay_in_the_strips():
    """A view_region outside every strip gets an error result, not an image."""
    view = {"x0": 1, "y0": 1, "x1": 5, "y1": 5, "overlay": False}
    run_, client = run(
        [
            reply(call("view_region", view)),
            reply(call("submit_corrections", FIX)),
            reply(text("ok"), stop="end_turn"),
        ]
    )
    result = client.requests[1]["messages"][-1]["content"][0]
    assert result["is_error"] and result["content"][0]["type"] == "text"
    assert run_.state == ReviewState.done


def test_refusal_or_output_limit_without_a_submission_fails():
    """No submission and a refusal (or max_tokens): the review failed; nothing to apply."""
    for stop in ("refusal", "max_tokens"):
        run_, _ = run([reply(text("no"), stop=stop)])
        assert run_.state == ReviewState.failed and run_.trace.stopped == stop


def test_deadline_already_passed_skips_without_a_request():
    """No time left: skipped, and nothing is sent."""
    run_, client = run([], deadline=time.monotonic() - 1)
    assert run_.state == ReviewState.skipped and client.requests == []


def test_api_error_after_a_submission_keeps_it():
    """A request that fails after a submission keeps that submission: done."""
    run_, _ = run([reply(call("submit_corrections", FIX)), api_error()])
    assert run_.state == ReviewState.done and run_.trace.answer == FIX
    assert isinstance(run_.error, anthropic.APIConnectionError)


def test_api_error_before_a_submission_fails_with_the_error():
    """A request that fails before any submission: failed, with the error kept."""
    run_, _ = run([api_error()])
    assert run_.state == ReviewState.failed
    assert isinstance(run_.error, anthropic.APIConnectionError)


def test_turn_limit_stops_the_review():
    """The review's own limits apply: one turn, no submission, failed."""
    run_, client = run(
        [reply(call("view_region", {"x0": 12, "y0": 1, "x1": 13, "y1": 5, "overlay": False}))],
        max_turns=1,
    )
    assert run_.state == ReviewState.failed and run_.trace.stopped == "turn limit"
    assert len(client.requests) == 1
