"""One pass with the scripted fake client: results, the map-size step, and every failure kind."""

import json
import logging

import anthropic
import httpx2
import pytest
from PIL import Image

from app import tracer as tracer_module
from app.config import load_settings
from app.domain import ChunkReport, MapSize, MapSizeSource, PassKind, TraceResult
from app.errors import LIMIT, FailureKind, PassFailure
from app.progress import ChunkBoard
from app.tracer import run_pass
from llm import agent
from llm.merge import chunk_layout, seams
from llm.orchestrator import ChunkState
from llm.review import ReviewState

from conftest import FIXTURES, FakeClient, RoutingFake, call, load_responses, reply, span, text

TEN = MapSize(width=10, height=10)
FALLBACK = MapSize(width=25, height=25)
ANSWER = {
    "walls": [{"points": [{"x": 1, "y": 1}, {"x": 9, "y": 1}]}],
    "arcs": [],
    "portals": [],
    "lights": [],
}


@pytest.fixture(scope="module")
def settings():
    """The shipped settings."""
    return load_settings()


@pytest.fixture
def image() -> Image.Image:
    """A plain 700 x 700 map image."""
    return Image.new("RGB", (700, 700), (90, 90, 90))


def ok_script() -> list:
    """The recorded quick-pass responses."""
    return load_responses(FIXTURES / "responses_quick_ok.json")


def size_reply(found: bool, width: int = 0, height: int = 0):
    """A reply to the map-size step."""
    return reply(call("report_map_size", {"grid_found": found, "width": width, "height": height}))


def test_quick_pass_returns_the_answer_in_fractions(image, settings):
    """The recorded responses become a TraceResult with counts, fractions, model and cost."""
    client = FakeClient(ok_script())
    result = run_pass(image, TEN, FALLBACK, PassKind.quick, settings, client)
    assert isinstance(result, TraceResult)
    assert (len(result.walls), len(result.portals), len(result.lights)) == (3, 1, 1)
    points = [p for w in result.walls for p in w.points] + [result.lights[0].at]
    assert all(0 <= p.fx <= 1 and 0 <= p.fy <= 1 for p in points)
    assert (result.model_id, result.effort) == ("claude-sonnet-5-5", "medium")
    assert result.cost_usd > 0 and result.usage.turns == 2
    assert result.traced_size == TEN and result.size_source == MapSizeSource.typed
    assert result.note.startswith("The answer matches")
    assert result.served_by == ["claude-sonnet-5-5"]
    assert {r["model"] for r in client.requests} == {"claude-sonnet-5-5"}


def test_missing_key_fails_without_a_request(image, settings, monkeypatch):
    """No key and no client: missing_key, and no client is ever made."""
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    monkeypatch.setattr(anthropic, "Anthropic", lambda *a, **k: pytest.fail("client created"))
    result = run_pass(image, TEN, FALLBACK, PassKind.quick, settings)
    assert isinstance(result, PassFailure) and result.kind == FailureKind.missing_key


def test_deep_pass_uses_opus_fresh_and_at_its_price(image, settings):
    """The deep pass asks Opus at medium effort, from scratch, priced with Opus's entry."""
    client = FakeClient(ok_script())
    result = run_pass(image, TEN, FALLBACK, PassKind.deep, settings, client)
    assert {(r["model"], r["output_config"]["effort"]) for r in client.requests} == {
        ("claude-opus-5-5", "medium")
    }
    first = client.requests[0]["messages"]
    assert len(first) == 1  # only the opening message: no earlier answer is sent
    price = settings.prices["claude-opus-5-5"]
    expected = (2000 * price.input + 200 * price.output) / 1e6
    assert result.cost_usd == pytest.approx(expected)
    assert result.model_id == "claude-opus-5-5"


# --- Failure kinds (contracts/ui.md) ---------------------------------------------------------

REQUEST = httpx2.Request("POST", "https://api.anthropic.com/v1/messages")


def status_error(cls, code: int):
    """An SDK status error of class `cls` with HTTP status `code`."""
    return cls("error", response=httpx2.Response(code, request=REQUEST), body=None)


@pytest.mark.parametrize(
    ("script", "kind"),
    [
        ([reply(text("no"), stop="refusal")], FailureKind.refusal),
        ([reply(text("..."), stop="max_tokens")], FailureKind.output_limit),
        ([status_error(anthropic.RateLimitError, 429)], FailureKind.rate_limit),
        ([status_error(anthropic.APIStatusError, 529)], FailureKind.provider_busy),
        ([status_error(anthropic.InternalServerError, 500)], FailureKind.provider_busy),
        ([status_error(anthropic.BadRequestError, 400)], FailureKind.unexpected),
        ([status_error(anthropic.NotFoundError, 404)], FailureKind.unexpected),
        ([status_error(anthropic.AuthenticationError, 401)], FailureKind.auth),
        ([status_error(anthropic.PermissionDeniedError, 403)], FailureKind.auth),
        ([anthropic.APIConnectionError(request=REQUEST)], FailureKind.network),
        ([anthropic.APITimeoutError(request=REQUEST)], FailureKind.timeout),
        ([RuntimeError("boom")], FailureKind.unexpected),
        (
            # The model never submits, even after the reminder.
            [reply(text("Looked."), stop="end_turn"), reply(text("Done."), stop="end_turn")],
            FailureKind.unreadable,
        ),
        (
            # A submission that fails validation (walls given as an object, not a list).
            [
                reply(call("submit_answer", {**ANSWER, "walls": {}})),
                reply(text("ok"), stop="end_turn"),
            ],
            FailureKind.unreadable,
        ),
    ],
)
def test_each_failure_cause_maps_to_its_kind(image, settings, script, kind):
    """Each cause gives its kind, nothing is raised, and detail and usage are filled in."""
    result = run_pass(image, TEN, FALLBACK, PassKind.quick, settings, FakeClient(script))
    assert isinstance(result, PassFailure)
    assert result.kind == kind and result.kind_of_pass == PassKind.quick
    assert result.detail and result.usage is not None


def test_usage_spent_before_an_error_is_reported(image, settings):
    """A failure after a paid turn still reports that turn's tokens and cost."""
    view = {"x0": 0, "y0": 0, "x1": 5, "y1": 5, "overlay": False}
    script = [reply(call("view_region", view)), anthropic.APIConnectionError(request=REQUEST)]
    result = run_pass(image, TEN, FALLBACK, PassKind.quick, settings, FakeClient(script))
    assert result.kind == FailureKind.network
    assert result.usage.input_tokens == 1000 and result.cost_usd > 0


@pytest.mark.parametrize("limit", [{"max_turns": 1}, {"max_cost_usd": 0.0001}])
def test_turn_or_cost_limit_without_an_answer_is_pass_limit(image, settings, limit, monkeypatch):
    """The loop's own limits with nothing submitted give pass_limit."""
    view = {"x0": 0, "y0": 0, "x1": 5, "y1": 5, "overlay": False}
    real = agent.load_config

    def limited(profile="quick", path=agent.CONFIG):
        """The real config with a tighter limit."""
        cfg = real(profile, path)
        cfg["limits"].update(limit)
        return cfg

    monkeypatch.setattr("app.tracer.load_config", limited)
    script = [reply(call("view_region", view))] * 3
    result = run_pass(image, TEN, FALLBACK, PassKind.quick, settings, FakeClient(script))
    assert result.kind == FailureKind.pass_limit


def test_passed_deadline_is_a_timeout(image, settings, monkeypatch):
    """A deadline that has passed before the first request gives timeout."""
    monkeypatch.setattr(
        settings.profiles["quick"], "deadline_s", -1.0
    )  # validated config forbids it; the test forces it
    result = run_pass(image, TEN, FALLBACK, PassKind.quick, settings, FakeClient([]))
    assert result.kind == FailureKind.timeout


# --- The map-size step ------------------------------------------------------------------------


def test_detected_size_is_used_and_reported(image, settings):
    """Size step reports 12 x 8; the trace uses it, and usage covers both steps."""
    client = FakeClient([size_reply(True, 12, 8), *ok_script()])
    result = run_pass(image, None, FALLBACK, PassKind.quick, settings, client)
    assert result.traced_size == MapSize(width=12, height=8)
    assert result.size_source == MapSizeSource.detected
    assert result.usage.input_tokens == 3000  # one size request and two loop requests
    assert (
        "12 squares wide and 8 squares high"
        in client.requests[1]["messages"][0]["content"][-1]["text"]
    )


def test_no_grid_traces_on_the_fallback_size(image, settings):
    """No grid found is a success on the fallback size, marked not_found."""
    client = FakeClient([size_reply(False), *ok_script()])
    result = run_pass(image, None, FALLBACK, PassKind.quick, settings, client)
    assert isinstance(result, TraceResult)
    assert result.traced_size == FALLBACK and result.size_source == MapSizeSource.not_found


def test_failure_in_the_size_step_is_a_pass_failure(image, settings):
    """An error during the size step fails the pass with the matching kind."""
    client = FakeClient([status_error(anthropic.RateLimitError, 429)])
    result = run_pass(image, None, FALLBACK, PassKind.quick, settings, client)
    assert isinstance(result, PassFailure) and result.kind == FailureKind.rate_limit


def test_refusal_in_the_size_step_is_a_refusal(image, settings):
    """A refusal of the size step fails the pass as a refusal, without tracing."""
    client = FakeClient([reply(text("no"), stop="refusal")])
    result = run_pass(image, None, FALLBACK, PassKind.quick, settings, client)
    assert result.kind == FailureKind.refusal and len(client.requests) == 1


def test_size_step_runs_on_opus_in_the_quick_pass_and_is_priced_as_opus(image, settings):
    """The quick pass asks Opus for the size, Sonnet for the trace, and adds both costs."""
    client = FakeClient([size_reply(True, 12, 8), *ok_script()])
    result = run_pass(image, None, FALLBACK, PassKind.quick, settings, client)
    models = [r["model"] for r in client.requests]
    assert models == ["claude-opus-5-5", "claude-sonnet-5-5", "claude-sonnet-5-5"]
    opus, sonnet = settings.prices["claude-opus-5-5"], settings.prices["claude-sonnet-5-5"]
    expected = (1000 * opus.input + 100 * opus.output) / 1e6
    expected += (2000 * sonnet.input + 200 * sonnet.output) / 1e6
    assert result.cost_usd == pytest.approx(expected)
    assert result.model_id == "claude-sonnet-5-5"  # the pass is still the quick one


def test_error_after_a_submission_keeps_the_answer(image, settings):
    """A request that fails after the model submitted (e.g. the deadline mid-check) keeps it."""
    script = [
        reply(call("submit_answer", ANSWER)),
        anthropic.APITimeoutError(request=REQUEST),
    ]
    result = run_pass(image, TEN, FALLBACK, PassKind.quick, settings, FakeClient(script))
    assert isinstance(result, TraceResult) and len(result.walls) == 1


def test_arc_with_no_radius_is_dropped_not_fatal(image, settings):
    """One degenerate arc is dropped; the rest of the answer is kept."""
    arc = {"cx": 5, "cy": 5, "r": 0, "start_deg": 0, "end_deg": 90}
    script = [
        reply(call("submit_answer", {**ANSWER, "arcs": [arc]})),
        reply(text("ok"), stop="end_turn"),
    ]
    result = run_pass(image, TEN, FALLBACK, PassKind.quick, settings, FakeClient(script))
    assert isinstance(result, TraceResult) and len(result.walls) == 1


def test_the_app_client_makes_no_retries(image, settings, monkeypatch):
    """The real client is built with max_retries=0, so a pass cannot outrun its deadline."""
    made = {}

    def fake(**kwargs):
        """Record the client's arguments and return a scripted client."""
        made.update(kwargs)
        return FakeClient(ok_script())

    monkeypatch.setenv("ANTHROPIC_API_KEY", "dummy")
    monkeypatch.setattr(anthropic, "Anthropic", fake)
    assert isinstance(run_pass(image, TEN, FALLBACK, PassKind.quick, settings), TraceResult)
    assert made == {"max_retries": 0}


# --- The chunked pass (feature 002) ----------------------------------------------------------


MAP25 = MapSize(width=25, height=25)
WINDOWS = [c.window for c in chunk_layout((25, 25), 13, 1, 4)]
LEFT_WALL = {"points": [{"x": 3, "y": 5}, {"x": 13.5, "y": 5.1}]}
RIGHT_WALL = {"points": [{"x": 11.5, "y": 4.9}, {"x": 22, "y": 5}]}


def chunk_answer(*walls) -> dict:
    """A chunk agent's submit_answer input."""
    return {"walls": list(walls), "arcs": [], "portals": [], "lights": []}


def submits(answer: dict) -> list:
    """An agent (or reviewer, with `tool`) that submits once and finishes."""
    return [reply(call("submit_answer", answer)), reply(text("Done."), stop="end_turn")]


def routes(review=None, **overrides) -> RoutingFake:
    """Four agents (two trace a wall across the seam), and a review script."""
    table = {
        span(WINDOWS[0]): submits(chunk_answer(LEFT_WALL)),
        span(WINDOWS[1]): submits(chunk_answer(RIGHT_WALL)),
        span(WINDOWS[2]): submits(chunk_answer()),
        span(WINDOWS[3]): submits(chunk_answer()),
        "review": review if review is not None else [reply(text("Fine."), stop="end_turn")] * 2,
    }
    for index, script in overrides.items():
        table[span(WINDOWS[int(index[1:])])] = script
    return RoutingFake(table)


@pytest.fixture
def big_image() -> Image.Image:
    """A plain 25 x 25 square map at 20 px per square."""
    return Image.new("RGB", (500, 500), (90, 90, 90))


def chunked(image, settings, client, size=MAP25, board=None, agents="sonnet"):
    """Run a chunked pass with the given fake client."""
    return run_pass(
        image, size, FALLBACK, PassKind.chunked, settings, client, agents=agents, board=board
    )


def logged(caplog) -> list[dict]:
    """The `battlemap` logger's records as parsed JSON."""
    return [json.loads(r.getMessage()) for r in caplog.records if r.name == "battlemap"]


def test_chunked_pass_returns_the_merged_mask_with_reports(big_image, settings, caplog):
    """Four agents and an orchestrator: one mask, a report per part, the review's report, the
    agents' and orchestrator's models, and every cost in the total."""
    client = routes()
    with caplog.at_level(logging.INFO, logger="battlemap"):
        result = chunked(big_image, settings, client)
    assert isinstance(result, TraceResult) and result.kind == PassKind.chunked
    assert len(result.walls) == 1  # the seam wall, joined
    assert result.agents == "sonnet" and result.model_id == "claude-sonnet-5-5"
    assert result.orchestrator_model == "claude-sonnet-5-5"
    assert [c.part for c in result.chunks] == [1, 2, 3, 4]
    assert result.chunks[0] == ChunkReport(
        part=1,
        state=ChunkState.done,
        seconds=result.chunks[0].seconds,
        cost_usd=result.chunks[0].cost_usd,
        walls=1,
    )
    assert result.review.state == ReviewState.failed  # the fake reviewer never submits
    assert result.review.model_label == "Sonnet 5.5"
    assert result.untraced == []
    assert result.cost_usd == pytest.approx(
        sum(c.cost_usd for c in result.chunks) + result.review.cost_usd
    )
    events = logged(caplog)
    finished = [e for e in events if e["event"] == "chunk_finished"]
    assert len(finished) == 4
    assert set(finished[0]) >= {
        "part",
        "window",
        "model",
        "state",
        "turns",
        "views",
        "submissions",
        "cost_usd",
        "elapsed_s",
    }
    assert finished[0]["window"] == span(WINDOWS[0])
    assert any(e["event"] == "review_finished" for e in events)
    final = [e for e in events if e["event"] == "pass_finished"][0]
    assert final["profile"] == "chunked" and final["chunks"] == 4 and final["agents"] == "sonnet"
    assert final["portals_dropped"] == 0 and final["lights_dropped"] == 0  # FR-013


def test_one_failed_part_gives_a_partial_result(big_image, settings):
    """A part that fails is reported with its kind and outlined as untraced."""
    client = routes(c1=[anthropic.APITimeoutError(request=REQUEST)])
    result = chunked(big_image, settings, client)
    assert isinstance(result, TraceResult)
    assert result.chunks[1].state == ChunkState.failed
    assert result.chunks[1].failure == FailureKind.timeout.value
    (corner_a, corner_b) = result.untraced[0]
    assert (corner_a.fx, corner_a.fy, corner_b.fx, corner_b.fy) == (0.5, 0, 1, 0.5)


def test_no_part_done_fails_with_the_first_failed_parts_kind(big_image, settings):
    """Every part fails: a PassFailure with the first failed part's kind."""
    refuse = [reply(text("no"), stop="refusal")]
    client = routes(
        c0=[anthropic.APIConnectionError(request=REQUEST)], c1=refuse, c2=refuse, c3=refuse
    )
    result = chunked(big_image, settings, client)
    assert isinstance(result, PassFailure) and result.kind == FailureKind.network
    assert result.kind_of_pass == PassKind.chunked


def test_every_part_skipped_is_a_pass_limit(big_image, settings, monkeypatch):
    """No time for any part: pass_limit."""
    monkeypatch.setattr(settings.chunked.agents["sonnet"], "deadline_s", 1e-9)
    result = chunked(big_image, settings, routes())
    assert isinstance(result, PassFailure) and result.kind == FailureKind.pass_limit


def test_chunked_missing_key_fails_before_any_request(big_image, settings, monkeypatch):
    """No key: missing_key, and no client is made."""
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    monkeypatch.setattr(anthropic, "Anthropic", lambda *a, **k: pytest.fail("client created"))
    result = run_pass(big_image, MAP25, FALLBACK, PassKind.chunked, settings, agents="sonnet")
    assert isinstance(result, PassFailure) and result.kind == FailureKind.missing_key


def test_detected_size_rebuilds_the_board_before_any_agent(big_image, settings):
    """With the size step on, the board is set for the detected size before agents start."""
    layout = chunk_layout((10, 10), 13, 1, 4)
    board = ChunkBoard(layout, seams(layout, (10, 10), 1.0))
    client = routes()
    client.routes["other"] = [size_reply(True, 25, 25)]
    result = chunked(big_image, settings, client, size=None, board=board)
    assert isinstance(result, TraceResult) and result.size_source == MapSizeSource.detected
    assert board.total == 4 and board.done_count() == 4


def test_a_failed_review_keeps_the_merged_mask(big_image, settings):
    """The reviewer's request fails: the merged mask stands, the review says why."""
    client = routes(review=[anthropic.APIConnectionError(request=REQUEST)])
    result = chunked(big_image, settings, client)
    assert isinstance(result, TraceResult) and len(result.walls) == 1
    assert result.review.state == ReviewState.failed
    assert result.review.failure == FailureKind.network.value


def status(cls, code):
    """An SDK status error with `code`."""
    return cls("x", response=httpx2.Response(code, request=REQUEST), body=None)


FAILURES = [
    (reply(text("no"), stop="refusal"), FailureKind.refusal),
    (reply(text("long"), stop="max_tokens"), FailureKind.output_limit),
    (status(anthropic.RateLimitError, 429), FailureKind.rate_limit),
    (status(anthropic.InternalServerError, 529), FailureKind.provider_busy),
    (status(anthropic.AuthenticationError, 401), FailureKind.auth),
    (anthropic.APIConnectionError(request=REQUEST), FailureKind.network),
    (anthropic.APITimeoutError(request=REQUEST), FailureKind.timeout),
]


@pytest.mark.parametrize(("item", "kind"), FAILURES, ids=[k.value for _, k in FAILURES])
def test_every_failure_kind_ends_a_part_or_the_review_plainly(big_image, settings, item, kind):
    """Each cause, once in a part and once in the review, gives a result, never an error."""
    result = chunked(big_image, settings, routes(c2=[item]))
    assert isinstance(result, TraceResult)
    assert result.chunks[2].state == ChunkState.failed and result.chunks[2].failure == kind.value
    result = chunked(big_image, settings, routes(review=[item]))
    assert isinstance(result, TraceResult)
    assert result.review.state == ReviewState.failed and result.review.failure == kind.value


def test_a_skipped_review_says_limit(big_image, settings, monkeypatch):
    """Agents used the whole budget: the review is skipped with the limit as its reason."""
    monkeypatch.setattr(settings.chunked.agents["sonnet"], "max_cost_usd", 0.001)
    monkeypatch.setattr(settings.chunked, "max_parallel", 4)
    result = chunked(big_image, settings, routes())
    assert isinstance(result, TraceResult)
    assert result.review.state == ReviewState.skipped and result.review.failure == LIMIT


def with_limits(monkeypatch, agent_turns: int = 16, **review):
    """Give every chunk agent `agent_turns` turns and change the review's limits."""
    original = tracer_module.load_chunked_config

    def tight(agents):
        """The shipped config with the agents' turn limit and the review's limits changed."""
        cfg = original(agents)
        cfg["limits"]["max_turns"] = agent_turns
        cfg["review"].update(review)
        return cfg

    monkeypatch.setattr(tracer_module, "load_chunked_config", tight)


def test_a_part_stopped_by_its_own_limit_reports_pass_limit(big_image, settings, monkeypatch):
    """Constitution IV: a chunk agent that hits its turn limit before submitting fails with
    pass_limit; the pass still returns its other parts."""
    with_limits(monkeypatch, agent_turns=1)
    view = {"x0": 1, "y0": 1, "x1": 4, "y1": 4, "overlay": False}
    client = routes(c3=[reply(call("view_region", view))])
    client.routes[span(WINDOWS[0])] = [reply(call("submit_answer", chunk_answer(LEFT_WALL)))]
    result = chunked(big_image, settings, client)
    assert isinstance(result, TraceResult)
    assert result.chunks[3].state == ChunkState.failed
    assert result.chunks[3].failure == FailureKind.pass_limit.value


def test_a_part_that_never_submits_reports_unreadable(big_image, settings):
    """Constitution IV: a chunk agent that finishes twice without a submission fails with
    unreadable."""
    silent = [reply(text("Looks empty."), stop="end_turn")] * 2
    result = chunked(big_image, settings, routes(c2=silent))
    assert isinstance(result, TraceResult)
    assert result.chunks[2].state == ChunkState.failed
    assert result.chunks[2].failure == FailureKind.unreadable.value


def test_a_review_stopped_by_its_limit_reports_pass_limit(big_image, settings, monkeypatch):
    """The review's own turn limit, with no submission: failed with pass_limit; merged mask
    kept."""
    with_limits(monkeypatch, max_turns=1)
    view = {"x0": 12, "y0": 1, "x1": 13, "y1": 5, "overlay": False}
    result = chunked(big_image, settings, routes(review=[reply(call("view_region", view))]))
    assert isinstance(result, TraceResult) and len(result.walls) == 1
    assert result.review.state == ReviewState.failed
    assert result.review.failure == FailureKind.pass_limit.value


def test_a_review_that_never_submits_reports_unreadable(big_image, settings):
    """The review finishes twice without a submission: failed with unreadable."""
    result = chunked(big_image, settings, routes())
    assert result.review.state == ReviewState.failed
    assert result.review.failure == FailureKind.unreadable.value
