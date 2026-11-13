"""One pass: the only place the app calls the model.

`run_pass` wraps the measured tool loop (`llm.agent.trace_map`) and, when the map size is not
given, the map-size step before it (`llm.agent.detect_map_size`), both inside one deadline and
one usage total. It never raises: every error and every bad stop becomes a `PassFailure` with a
kind the page has a message for (research.md R6, contracts/ui.md).
"""

import os
import time

import anthropic
from PIL import Image
from pydantic import ValidationError

from app.config import Settings
from app.domain import (
    MapSize,
    MapSizeSource,
    PassKind,
    RawAnswer,
    TraceResult,
    Usage,
    answer_to_fractions,
)
from app.errors import FailureKind, PassFailure
from app.logging import log_event
from llm.agent import Trace, detect_map_size, load_config, size_step_config, trace_map

# The loop's own stop reasons that end a pass without a usable answer.
STOP_KINDS = {
    "refusal": FailureKind.refusal,
    "max_tokens": FailureKind.output_limit,
    "turn limit": FailureKind.pass_limit,
    "cost limit": FailureKind.pass_limit,
    "timeout": FailureKind.timeout,
}


class _Stop(Exception):
    """Internal: ends a pass early with a failure kind and a detail for the log."""

    def __init__(self, kind: FailureKind, detail: str):
        """Keep the kind and the detail."""
        super().__init__(detail)
        self.kind, self.detail = kind, detail


def classify(error: BaseException) -> FailureKind:
    """The failure kind for an exception raised during a pass."""
    # APITimeoutError is a kind of APIConnectionError, and RateLimitError, AuthenticationError
    # and PermissionDeniedError are kinds of APIStatusError, so the order matters.
    if isinstance(error, _Stop):
        return error.kind
    if isinstance(error, anthropic.APITimeoutError):
        return FailureKind.timeout
    if isinstance(error, anthropic.APIConnectionError):
        return FailureKind.network
    if isinstance(error, anthropic.RateLimitError):
        return FailureKind.rate_limit
    if isinstance(error, anthropic.AuthenticationError | anthropic.PermissionDeniedError):
        return FailureKind.auth
    if isinstance(error, anthropic.APIStatusError) and error.status_code >= 500:
        return FailureKind.provider_busy  # 5xx, and 529 overloaded
    # Other 4xx (bad request, unknown model, request too large): retrying will not help.
    if isinstance(error, ValidationError):
        return FailureKind.unreadable
    return FailureKind.unexpected


def usage_of(trace: Trace) -> Usage:
    """The trace's token counts and loop counters."""
    return Usage(
        input_tokens=trace.input_tokens,
        output_tokens=trace.output_tokens,
        cache_write_tokens=trace.cache_write_tokens,
        cache_read_tokens=trace.cache_read_tokens,
        turns=trace.turns,
        views=trace.views,
        submissions=trace.submissions,
    )


def _log_fields(trace: Trace, kind: PassKind, model: str, elapsed: float) -> dict:
    """The fields every pass event carries: profile, model, time, tokens, cost."""
    return {
        "profile": kind.value,
        "model": model,
        "served_by": sorted(trace.served_by),
        "elapsed_s": round(elapsed, 1),
        "cost_usd": round(trace.cost_usd, 4),
        **usage_of(trace).model_dump(),
    }


def run_pass(
    image: Image.Image,
    map_size: MapSize | None,
    fallback_size: MapSize,
    kind: PassKind,
    settings: Settings,
    client: anthropic.Anthropic | None = None,
    size_source: MapSizeSource = MapSizeSource.typed,
) -> TraceResult | PassFailure:
    """Trace one map with the profile for `kind`; never raises.

    `map_size` is the size to trace with, or None to let the model work it out first;
    `fallback_size` is used when it finds no grid. `size_source` is what to report when the
    size was given (typed or the untouched default). `client` lets tests pass a fake one;
    without it, a missing `ANTHROPIC_API_KEY` fails before any request.
    """
    start = time.monotonic()
    profile = settings.profiles[kind]
    trace = Trace()
    try:
        if client is None:
            if not os.environ.get("ANTHROPIC_API_KEY"):
                raise _Stop(FailureKind.missing_key, "ANTHROPIC_API_KEY is not set")
            # No SDK retries: each retry would get the whole time left again and could run the
            # pass far past its deadline and bill it twice. A failed pass says "try again".
            client = anthropic.Anthropic(max_retries=0)
        cfg = load_config(kind.value)
        deadline = start + profile.deadline_s

        traced, source = map_size, size_source
        if map_size is None:
            # The size step uses its own profile's model (Opus) in both passes.
            found = detect_map_size(image, size_step_config(), client, trace, deadline)
            if trace.stopped in STOP_KINDS:
                raise _Stop(STOP_KINDS[trace.stopped], f"map-size step: {trace.stopped}")
            if found is not None:
                traced, source = MapSize(width=found[0], height=found[1]), MapSizeSource.detected
            else:
                traced, source = fallback_size, MapSizeSource.not_found

        try:
            trace_map(image, traced.as_tuple(), cfg, client, deadline=deadline, trace=trace)
        except anthropic.APIError as error:
            # A request that fails after a submission (often the deadline running out during
            # the model's check of its own answer) keeps that submission: it was paid for.
            if trace.answer is None:
                raise
            trace.stopped = f"kept last submission after {type(error).__name__}"
        if trace.answer is None:
            # Limits and deadlines with an answer keep it: the last submission stands.
            stop_kind = STOP_KINDS.get(trace.stopped, FailureKind.unreadable)
            raise _Stop(stop_kind, f"no answer; loop stopped: {trace.stopped or 'unknown'}")
        if trace.stopped in ("refusal", "max_tokens"):
            raise _Stop(STOP_KINDS[trace.stopped], f"loop stopped: {trace.stopped}")

        raw = RawAnswer.model_validate(trace.answer)
        walls, portals, lights = answer_to_fractions(raw, traced, image.size)
        elapsed = time.monotonic() - start
        result = TraceResult(
            walls=walls,
            portals=portals,
            lights=lights,
            note=trace.note,
            kind=kind,
            model_id=profile.name,
            served_by=sorted(trace.served_by),
            effort=profile.effort,
            elapsed_s=elapsed,
            usage=usage_of(trace),
            cost_usd=trace.cost_usd,
            traced_size=traced,
            size_source=source,
        )
        log_event(
            "pass_finished",
            **_log_fields(trace, kind, profile.name, elapsed),
            stopped=trace.stopped,
            map_size=f"{traced.width}x{traced.height}",
            size_source=source.value,
            walls=len(walls),
            portals=len(portals),
            lights=len(lights),
        )
        return result
    except Exception as error:  # noqa: BLE001 - every cause becomes a typed failure
        failure_kind = classify(error)
        elapsed = time.monotonic() - start
        detail = getattr(error, "detail", None) or f"{type(error).__name__}: {error}"
        log_event(
            "pass_failed",
            **_log_fields(trace, kind, profile.name, elapsed),
            failure=failure_kind.value,
            detail=detail,
        )
        return PassFailure(
            kind=failure_kind,
            kind_of_pass=kind,
            elapsed_s=elapsed,
            usage=usage_of(trace),
            cost_usd=trace.cost_usd,
            detail=detail,
        )
