"""The chunked-pass orchestrator: config loading, chunk agents, merge and seam review, all with
scripted fake clients (no network, no cost)."""

import time

import anthropic
import httpx2
import pytest
from PIL import Image

from data.rasterize import decode_image, load_uvtt
from llm.orchestrator import (
    ChunkState,
    chunk_layout,
    default_agents,
    load_chunked_config,
    trace_chunks,
)
from llm.review import ReviewState
from postprocess.uvtt import answer_to_uvtt, write_uvtt

from conftest import DEMO_MAP, RoutingFake, call, reply, span, text


@pytest.mark.parametrize(
    ("agents", "agent_model", "review_model"),
    [
        ("haiku", "claude-haiku-5-5", "claude-sonnet-5-5"),
        ("sonnet", "claude-sonnet-5-5", "claude-sonnet-5-5"),
        ("opus", "claude-opus-5-5", "claude-opus-5-5"),
    ],
)
def test_load_chunked_config_pairs_the_agents_with_their_orchestrator(
    agents, agent_model, review_model
):
    """Each choice gives its agents' model, and the orchestrator model the constitution pairs
    with it (Sonnet for Haiku and Sonnet agents, Opus for Opus agents)."""
    cfg = load_chunked_config(agents)
    assert cfg["model"]["name"] == agent_model
    assert cfg["review"]["model"]["name"] == review_model
    assert cfg["chunked"]["agents"] == agents


def test_load_chunked_config_uses_the_chunk_limits_and_the_review_table():
    """Agents get [chunked.limits], not the single session's [limits]; the review gets
    [chunked.review]; the choice's whole-pass limits and the shared tables come along."""
    cfg = load_chunked_config("sonnet")
    assert cfg["limits"] == {
        "max_turns": 16,
        "max_views": 8,
        "max_submissions": 2,
        "max_cost_usd": 0.75,
    }
    assert cfg["review"]["strip_squares"] == 1.0 and cfg["review"]["max_views"] == 6
    assert cfg["chunked"]["deadline_s"] == 180 and cfg["chunked"]["max_cost_usd"] == 2.5
    assert cfg["chunked"]["orchestrator"] == "sonnet"
    assert cfg["chunked"]["core_squares"] == 13 and cfg["chunked"]["max_parallel"] == 4
    assert "claude-sonnet-5-5" in cfg["prices"] and "max_px" in cfg["views"]


def test_load_chunked_config_rejects_an_unknown_choice():
    """Only the choices in [chunked.agents] exist."""
    with pytest.raises(ValueError, match="fable"):
        load_chunked_config("fable")


# --- trace_chunks (T022, T024) ---------------------------------------------------------------


REQUEST = httpx2.Request("POST", "https://api.anthropic.com/v1/messages")
WINDOWS = [c.window for c in chunk_layout((25, 25), 13, 1, 4)]
WALL_LEFT = {"points": [{"x": 3, "y": 5}, {"x": 13.5, "y": 5.1}]}
WALL_RIGHT = {"points": [{"x": 11.5, "y": 4.9}, {"x": 22, "y": 5}]}
DOOR = {"x1": 11.8, "y1": 8, "x2": 12.2, "y2": 8}
LIGHT = {"x": 13, "y": 3, "tier": "small"}


def answer(walls=(), portals=(), lights=()) -> dict:
    """A submit_answer input."""
    return {"walls": list(walls), "arcs": [], "portals": list(portals), "lights": list(lights)}


def agent_script(ans: dict) -> list:
    """An agent that submits once and finishes."""
    return [reply(call("submit_answer", ans)), reply(text("Done."), stop="end_turn")]


def four_agents(review: list | None = None) -> RoutingFake:
    """Four agents: the top two both trace a wall across x = 12.5 and report the same door
    and light; the bottom two report nothing. The review submits nothing new by default."""
    top = answer([WALL_LEFT], [DOOR], [LIGHT])
    routes = {
        span(WINDOWS[0]): agent_script({**top, "walls": [WALL_LEFT]}),
        span(WINDOWS[1]): agent_script({**top, "walls": [WALL_RIGHT]}),
        span(WINDOWS[2]): agent_script(answer()),
        span(WINDOWS[3]): agent_script(answer()),
    }
    if review is not None:
        routes["review"] = review
    return RoutingFake(routes)


def config(**chunked) -> dict:
    """The Sonnet choice's config, with `[chunked]` settings overridden."""
    cfg = load_chunked_config("sonnet")
    cfg["chunked"].update(chunked)
    return cfg


def demo_image() -> Image.Image:
    """The demo map's image at 70 px per square (25 x 25 squares)."""
    return decode_image(load_uvtt(DEMO_MAP))


def keep_merged() -> list:
    """A reviewer that resubmits the strips' content unchanged except for a light it adds."""
    fix = answer(
        [{"points": [{"x": 11.5, "y": 5}, {"x": 13.5, "y": 5}]}],
        [DOOR],
        [LIGHT, {"x": 12.5, "y": 20, "tier": "medium"}],
    )
    return [reply(call("submit_corrections", fix)), reply(text("ok"), stop="end_turn")]


def test_four_agents_and_a_reviewer_give_one_final_answer():
    """Every chunk done, the merge joins the seam wall and keeps the door and light once,
    and the review's submission is applied inside the strips."""
    result = trace_chunks(demo_image(), (25, 25), config(), four_agents(keep_merged()))
    assert [r.state for r in result.runs] == [ChunkState.done] * 4
    assert len(result.merged["walls"]) == 1
    assert result.merged["portals"] == [DOOR] and result.merged["lights"] == [LIGHT]
    assert result.merge.joins == 1
    assert result.review.state == ReviewState.done
    assert result.review.added["lights"] == 2 and result.review.removed["lights"] == 1
    assert {"x": 12.5, "y": 20, "tier": "medium"} in result.answer["lights"]
    assert (
        result.cost_usd == sum(r.trace.cost_usd for r in result.runs) + result.review.trace.cost_usd
    )
    assert result.runs[0].counts() == {"walls": 1, "portals": 1, "lights": 1}


def test_one_agent_at_a_time_starts_in_order():
    """With max_parallel = 1 the agents run in index order."""
    client = four_agents([])
    order = []
    trace_chunks(
        demo_image(),
        (25, 25),
        config(max_parallel=1),
        client,
        on_update=lambda kind, i, state: (
            order.append(i) if kind == "chunk" and state == ChunkState.tracing else None
        ),
    )
    assert order == [0, 1, 2, 3]


def test_a_deadline_already_passed_skips_every_chunk_and_sends_nothing():
    """No time: every chunk is skipped, no request is made, and there is no answer."""
    client = four_agents()
    result = trace_chunks(demo_image(), (25, 25), config(), client, deadline=time.monotonic() - 1)
    assert [r.state for r in result.runs] == [ChunkState.skipped] * 4
    assert client.requests == {}
    assert result.merged is None and result.answer is None
    assert result.review.state == ReviewState.skipped


def test_the_cost_limit_skips_the_chunks_not_started():
    """Once the chunks so far cost the choice's limit, the rest are skipped."""
    result = trace_chunks(
        demo_image(), (25, 25), config(max_parallel=1, max_cost_usd=0.001), four_agents([])
    )
    assert [r.state for r in result.runs] == [ChunkState.done] + [ChunkState.skipped] * 3
    assert result.untraced == [c.core for c in result.layout[1:]]


@pytest.mark.parametrize(
    "error",
    [
        anthropic.APITimeoutError(request=REQUEST),
        anthropic.APIConnectionError(request=REQUEST),
        anthropic.RateLimitError("x", response=httpx2.Response(429, request=REQUEST), body=None),
        anthropic.AuthenticationError(
            "x", response=httpx2.Response(401, request=REQUEST), body=None
        ),
        anthropic.InternalServerError(
            "x", response=httpx2.Response(500, request=REQUEST), body=None
        ),
    ],
    ids=["timeout", "network", "rate_limit", "auth", "server"],
)
def test_one_failed_agent_leaves_the_others(error):
    """An agent whose request raises fails, with its error kept; the others finish."""
    client = four_agents([])
    client.routes[span(WINDOWS[1])] = [error]
    result = trace_chunks(demo_image(), (25, 25), config(), client)
    states = [r.state for r in result.runs]
    assert states == [ChunkState.done, ChunkState.failed, ChunkState.done, ChunkState.done]
    assert result.runs[1].error is error
    assert result.untraced == [result.layout[1].core]


@pytest.mark.parametrize("stop", ["refusal", "max_tokens"])
def test_an_agent_that_stops_without_an_answer_fails(stop):
    """A refusal or output limit before any submission: failed, others unaffected."""
    client = four_agents([])
    client.routes[span(WINDOWS[2])] = [reply(text("no"), stop=stop)]
    result = trace_chunks(demo_image(), (25, 25), config(), client)
    assert result.runs[2].state == ChunkState.failed
    assert result.runs[2].trace.stopped == stop


def test_an_agent_that_raises_after_a_submission_is_done():
    """A submission followed by an API error keeps the submission."""
    client = four_agents([])
    client.routes[span(WINDOWS[0])] = [
        reply(call("submit_answer", answer([WALL_LEFT]))),
        anthropic.APIConnectionError(request=REQUEST),
    ]
    result = trace_chunks(demo_image(), (25, 25), config(), client)
    assert result.runs[0].state == ChunkState.done
    assert isinstance(result.runs[0].error, anthropic.APIConnectionError)


def test_no_chunk_done_means_no_answer_and_no_review():
    """Every agent fails: nothing to merge and nothing to review."""
    client = RoutingFake({span(w): [reply(text("no"), stop="refusal")] for w in WINDOWS})
    result = trace_chunks(demo_image(), (25, 25), config(), client)
    assert result.merged is None and result.answer is None
    assert result.review.state == ReviewState.skipped
    assert "review" not in client.requests


def test_a_one_chunk_map_needs_no_review():
    """A 13 x 13 map is one chunk: no seams, so the review is not needed."""
    image = Image.new("RGB", (13 * 70, 13 * 70), (90, 90, 90))
    client = RoutingFake({span((0, 0, 13, 13)): agent_script(answer([WALL_LEFT]))})
    result = trace_chunks(image, (13, 13), config(), client)
    assert result.review.state == ReviewState.not_needed
    assert result.answer == result.merged and len(result.answer["walls"]) == 1


def test_on_update_reports_states_and_its_errors_are_ignored():
    """Every chunk goes waiting -> tracing -> done; the review reports too; a callback that
    raises does not stop the pass."""
    seen = []

    def callback(kind, index, state):
        """Record the update, then fail, as a buggy page callback might."""
        seen.append((kind, index, state))
        raise RuntimeError("page closed")

    result = trace_chunks(demo_image(), (25, 25), config(), four_agents([]), on_update=callback)
    for i in range(4):
        mine = [s for k, j, s in seen if k == "chunk" and j == i]
        assert mine == [ChunkState.tracing, ChunkState.done]
    review = [s for k, _, s in seen if k == "review"]
    assert review[0] == ReviewState.reviewing and review[-1] == result.review.state


def test_views_are_saved_per_chunk_and_for_the_review(tmp_path):
    """With out_dir, each agent's and the reviewer's images are written."""
    trace_chunks(demo_image(), (25, 25), config(), four_agents(keep_merged()), out_dir=tmp_path)
    for i in range(4):
        assert any((tmp_path / "chunks" / str(i) / "views").glob("*.jpg"))
    assert any((tmp_path / "review" / "views").glob("*.jpg"))


def test_four_agents_give_one_valid_file(tmp_path):
    """US1 end to end: the final answer exports as one Universal VTT file that loads, with one
    continuous wall across the seam and the door and light once."""
    result = trace_chunks(demo_image(), (25, 25), config(), four_agents([]))
    path = tmp_path / "map.dd2vtt"
    write_uvtt(path, answer_to_uvtt(result.answer, (25, 25)))
    uvtt = load_uvtt(path)
    assert uvtt["resolution"]["map_size"] == {"x": 25, "y": 25}
    (wall,) = uvtt["line_of_sight"]
    assert wall[0] == {"x": 3, "y": 5} and wall[-1] == {"x": 22, "y": 5}
    assert len(uvtt["portals"]) == 1 and len(uvtt["lights"]) == 1


def test_the_review_cannot_take_the_pass_past_its_cost_limit():
    """FR-020 / FR-010: the review gets only the whole-map budget the agents left. Four agents
    cost 4 x $0.006; with a $0.0265 limit the review may make one $0.003 request, then stops."""
    view = {"x0": 12, "y0": 1, "x1": 13, "y1": 5, "overlay": False}
    client = four_agents([reply(call("view_region", view))] * 5)
    result = trace_chunks(demo_image(), (25, 25), config(max_cost_usd=0.0265), client)
    assert result.review.trace.turns == 1
    assert result.review.trace.stopped == "cost limit"
    assert result.cost_usd == pytest.approx(0.027)


def test_cost_spent_before_the_agents_counts_toward_the_limit():
    """FR-010: a size step that used the whole budget leaves nothing for the agents."""
    client = four_agents()
    result = trace_chunks(
        demo_image(), (25, 25), config(max_cost_usd=0.03), client, spent_before=0.03
    )
    assert [r.state for r in result.runs] == [ChunkState.skipped] * 4
    assert client.requests == {}
    assert result.cost_usd == 0  # the orchestrator's own spend; the caller adds the size step


def test_default_agents_comes_from_the_config():
    """The selector's default is [chunked].default_agents, not a literal in code."""
    assert default_agents() == "sonnet"
