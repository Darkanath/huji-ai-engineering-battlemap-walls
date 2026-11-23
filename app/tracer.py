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
    AgentChoice,
    ChunkReport,
    MapSize,
    MapSizeSource,
    PassKind,
    Point,
    RawAnswer,
    ReviewReport,
    TraceResult,
    Usage,
    answer_to_fractions,
)
from app.errors import LIMIT, FailureKind, PassFailure
from app.logging import log_event
from app.progress import ChunkBoard
from llm.agent import Trace, detect_map_size, load_config, size_step_config, trace_map
from llm.merge import seams
from llm.orchestrator import ChunkedTrace, ChunkRun, ChunkState, load_chunked_config, trace_chunks
from llm.review import ReviewRun, ReviewState

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


def _client(client: anthropic.Anthropic | None) -> anthropic.Anthropic:
    """The client to use: the one given (tests), or a new one; `_Stop` when no key is set."""
    if client is not None:
        return client
    if not os.environ.get("ANTHROPIC_API_KEY"):
        raise _Stop(FailureKind.missing_key, "ANTHROPIC_API_KEY is not set")
    # No SDK retries: each retry would get the whole time left again and could run the
    # pass far past its deadline and bill it twice. A failed pass says "try again".
    return anthropic.Anthropic(max_retries=0)


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
    agents: AgentChoice | None = None,
    board: ChunkBoard | None = None,
) -> TraceResult | PassFailure:
    """Trace one map with the profile for `kind`; never raises.

    `map_size` is the size to trace with, or None to let the model work it out first;
    `fallback_size` is used when it finds no grid. `size_source` is what to report when the
    size was given (typed or the untouched default). `client` lets tests pass a fake one;
    without it, a missing `ANTHROPIC_API_KEY` fails before any request.

    `kind == PassKind.chunked` runs the chunked pass instead (`agents` picks the agents'
    model, default `[chunked].default_agents`; `board` is updated live for the page).
    """
    if kind == PassKind.chunked:
        return _chunked_pass(
            image, map_size, fallback_size, settings, client, size_source, agents, board
        )
    start = time.monotonic()
    profile = settings.profiles[kind]
    trace = Trace()
    try:
        client = _client(client)
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


# --- The chunked pass (specs/002-chunked-map-tracing/contracts/app.md) -----------------------


def _usage_sum(traces: list[Trace]) -> Usage:
    """Token counts and loop counters summed over several traces."""
    parts = [usage_of(t).model_dump() for t in traces]
    return Usage(**{k: sum(p[k] for p in parts) for k in parts[0]}) if parts else Usage()


def _stop_failure(trace: Trace, error: BaseException | None) -> FailureKind:
    """Why an agent or the review ended with nothing: its exception, else its stop reason."""
    if error is not None:
        return classify(error)
    return STOP_KINDS.get(trace.stopped, FailureKind.unreadable)


def _chunk_failure(run: ChunkRun) -> str | None:
    """A part's failure for its report: None when done, LIMIT when skipped."""
    if run.state == ChunkState.done:
        return None
    if run.state == ChunkState.skipped:
        return LIMIT
    return _stop_failure(run.trace, run.error).value


def _review_report(review: ReviewRun, label: str) -> ReviewReport:
    """The seam review's row for the agent table."""
    failure = None
    if review.state == ReviewState.failed:
        failure = _stop_failure(review.trace, review.error).value
    elif review.state == ReviewState.skipped:
        failure = LIMIT
    return ReviewReport(
        state=review.state,
        failure=failure,
        model_label=label,
        seconds=review.seconds,
        cost_usd=review.trace.cost_usd,
        removed=review.removed,
        added=review.added,
    )


def _span(box) -> str:
    """ "x 0 to 13.5, y 0 to 13.5", as the agent's intro names its window."""
    return f"x {box[0]:g} to {box[2]:g}, y {box[1]:g} to {box[3]:g}"


def _log_chunked(result: ChunkedTrace, cfg: dict) -> None:
    """One `chunk_finished` line per part and one `review_finished` line (spec FR-013)."""
    for run in result.runs:
        log_event(
            "chunk_finished",
            part=run.chunk.index + 1,
            window=_span(run.chunk.window),
            model=cfg["model"]["name"],
            state=run.state.value,
            failure=_chunk_failure(run),
            turns=run.trace.turns,
            views=run.trace.views,
            submissions=run.trace.submissions,
            cost_usd=round(run.trace.cost_usd, 4),
            elapsed_s=round(run.seconds, 1),
        )
    review = result.review
    log_event(
        "review_finished",
        state=review.state.value,
        model=review.model,
        turns=review.trace.turns,
        views=review.trace.views,
        cost_usd=round(review.trace.cost_usd, 4),
        elapsed_s=round(review.seconds, 1),
        removed=review.removed,
        added=review.added,
    )


def _chunked_pass(
    image: Image.Image,
    map_size: MapSize | None,
    fallback_size: MapSize,
    settings: Settings,
    client: anthropic.Anthropic | None,
    size_source: MapSizeSource,
    agents: AgentChoice | None,
    board: ChunkBoard | None,
) -> TraceResult | PassFailure:
    """The chunked pass: size step (when asked), the orchestrator, then the result; never
    raises. Limits and parallelism come from the validated settings."""
    start = time.monotonic()
    chunked = settings.chunked
    agents = agents or chunked.default_agents
    choice = chunked.agents[agents]
    size_trace = Trace()
    traces: list[Trace] = [size_trace]
    fields = {"profile": PassKind.chunked.value, "model": choice.name, "agents": agents}
    try:
        client = _client(client)
        cfg = load_chunked_config(agents)
        cfg["chunked"].update(max_cost_usd=choice.max_cost_usd, max_parallel=chunked.max_parallel)
        deadline = start + choice.deadline_s

        traced, source = map_size, size_source
        if map_size is None:
            found = detect_map_size(image, size_step_config(), client, size_trace, deadline)
            if size_trace.stopped in STOP_KINDS:
                raise _Stop(STOP_KINDS[size_trace.stopped], f"map-size step: {size_trace.stopped}")
            if found is not None:
                traced, source = MapSize(width=found[0], height=found[1]), MapSizeSource.detected
            else:
                traced, source = fallback_size, MapSizeSource.not_found
            if board is not None:
                layout = chunked.layout(traced.as_tuple(), agents)
                board.rebuild(
                    layout, seams(layout, traced.as_tuple(), chunked.review.strip_squares)
                )

        result = trace_chunks(
            image,
            traced.as_tuple(),
            cfg,
            client,
            deadline=deadline,
            on_update=board.on_update if board is not None else None,
            spent_before=size_trace.cost_usd,
        )
        traces += [r.trace for r in result.runs] + [result.review.trace]
        _log_chunked(result, cfg)
        if result.answer is None:
            failed = result.by_state(ChunkState.failed)
            kind = (
                _stop_failure(failed[0].trace, failed[0].error)
                if failed
                else FailureKind.pass_limit
            )
            raise _Stop(
                kind,
                f"no part traced: {len(failed)} failed, "
                f"{len(result.by_state(ChunkState.skipped))} skipped",
            )

        raw = RawAnswer.model_validate(result.answer)
        walls, portals, lights = answer_to_fractions(raw, traced, image.size)
        width_ppg = image.width / traced.width

        def frac(x: float, y: float) -> Point:
            """A point in squares as image fractions, as answer_to_fractions converts it."""
            return Point(fx=x / traced.width, fy=y * width_ppg / image.height)

        elapsed = time.monotonic() - start
        orchestrator = chunked.agents[choice.orchestrator]
        outcome = TraceResult(
            walls=walls,
            portals=portals,
            lights=lights,
            note=result.review.trace.note,
            kind=PassKind.chunked,
            model_id=choice.name,
            served_by=sorted(set().union(*(t.served_by for t in traces))),
            effort=choice.effort,
            elapsed_s=elapsed,
            usage=_usage_sum(traces),
            cost_usd=sum(t.cost_usd for t in traces),
            traced_size=traced,
            size_source=source,
            agents=agents,
            orchestrator_model=orchestrator.name,
            chunks=[
                ChunkReport(
                    part=r.chunk.index + 1,
                    state=r.state,
                    failure=_chunk_failure(r),
                    seconds=r.seconds,
                    cost_usd=r.trace.cost_usd,
                    views=r.trace.views,
                    **r.counts(),
                )
                for r in result.runs
            ],
            review=_review_report(result.review, orchestrator.label),
            untraced=[(frac(b[0], b[1]), frac(b[2], b[3])) for b in result.untraced],
        )
        merge = result.merge
        log_event(
            "pass_finished",
            **fields,
            orchestrator=orchestrator.name,
            elapsed_s=round(elapsed, 1),
            cost_usd=round(outcome.cost_usd, 4),
            map_size=f"{traced.width}x{traced.height}",
            size_source=source.value,
            chunks=len(result.runs),
            chunks_failed=len(result.by_state(ChunkState.failed)),
            chunks_skipped=len(result.by_state(ChunkState.skipped)),
            review=result.review.state.value,
            joins=merge.joins if merge else 0,
            ends_snapped=merge.ends_snapped if merge else 0,
            pieces_dropped=merge.pieces_dropped if merge else 0,
            walls_deduped=merge.walls_deduped if merge else 0,
            portals_dropped=sum(merge.portals_dropped) if merge else 0,
            lights_dropped=sum(merge.lights_dropped) if merge else 0,
            walls=len(walls),
            portals=len(portals),
            lights=len(lights),
        )
        return outcome
    except Exception as error:  # noqa: BLE001 - every cause becomes a typed failure
        failure_kind = classify(error)
        elapsed = time.monotonic() - start
        detail = getattr(error, "detail", None) or f"{type(error).__name__}: {error}"
        cost = sum(t.cost_usd for t in traces)
        log_event(
            "pass_failed",
            **fields,
            elapsed_s=round(elapsed, 1),
            cost_usd=round(cost, 4),
            failure=failure_kind.value,
            detail=detail,
        )
        return PassFailure(
            kind=failure_kind,
            kind_of_pass=PassKind.chunked,
            elapsed_s=elapsed,
            usage=_usage_sum(traces),
            cost_usd=cost,
            detail=detail,
        )
