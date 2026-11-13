"""One pass with the scripted fake client: results, the map-size step, and every failure kind."""

import anthropic
import httpx2
import pytest
from PIL import Image

from app.config import load_settings
from app.domain import MapSize, MapSizeSource, PassKind, TraceResult
from app.errors import FailureKind, PassFailure
from app.tracer import run_pass
from llm import agent

from conftest import FIXTURES, FakeClient, call, load_responses, reply, text

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
