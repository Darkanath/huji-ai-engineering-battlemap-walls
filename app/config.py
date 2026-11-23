"""The app's settings, validated from the tracer's config file (`llm/configs/claude.toml`).

The tool loop in `llm/agent.py` reads the same file as a plain dict; this module checks it once
for the app: every profile has a price, every light tier has a range, deadlines are positive.
"""

import math
import tomllib
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, Field, model_validator

from app.domain import MAX_SQUARES, MIN_SQUARES, AgentChoice
from llm.agent import CONFIG
from llm.merge import Chunk, chunk_layout

TIERS = ("small", "medium", "large")


class Profile(BaseModel):
    """One model profile: which model a pass uses and what the user is told to expect."""

    name: str  # model id
    label: str  # shown in the status line, e.g. "Sonnet 5.5"
    effort: str
    max_tokens: int = Field(gt=0)
    fallbacks: bool
    deadline_s: float = Field(gt=0)
    expected_seconds: float = Field(ge=0)
    expected_cost_usd: float = Field(ge=0)


class Limits(BaseModel):
    """Per-map limits of the tool loop."""

    max_turns: int = Field(gt=0)
    max_views: int = Field(ge=0)
    max_submissions: int = Field(gt=0)
    max_cost_usd: float = Field(gt=0)


class Views(BaseModel):
    """How the images sent to the model are drawn."""

    max_px: int = Field(gt=0)
    max_zoom: float = Field(gt=0)
    jpeg_quality: int = Field(ge=1, le=100)
    quadrants: bool = True


class Price(BaseModel):
    """USD per million tokens for one model."""

    input: float = Field(ge=0)
    output: float = Field(ge=0)


class LightSpec(BaseModel):
    """What the exported file says for one light tier."""

    range: float = Field(gt=0)  # grid squares
    intensity: float = Field(gt=0)


class AppLimits(BaseModel):
    """Upload and map-size limits, and the export's scale and quality."""

    max_upload_mb: float = Field(gt=0)
    min_squares: int = Field(ge=1)
    max_squares: int = Field(ge=1)
    default_width: int = Field(ge=1)
    default_height: int = Field(ge=1)
    export_ppg: int = Field(gt=0)
    export_jpeg_quality: int = Field(ge=1, le=100)
    detect_size_default: bool = False  # the detect option's state for a new upload


class SizeStep(BaseModel):
    """Which profile's model works out the map size, in both passes."""

    profile: Literal["quick", "deep"]
    expected_cost_usd: float = Field(ge=0)
    expected_seconds: float = Field(default=8, ge=0)  # used in the chunked button's figures


class AgentSettings(BaseModel):
    """One choice in the chunked pass's selector: the agents' model, its orchestrator, its
    whole-pass limits and its expected figures (estimates until measured)."""

    core_squares: float = Field(ge=2)  # this model's part size (largest side of a core)
    name: str
    label: str
    effort: str
    max_tokens: int = Field(gt=0)
    fallbacks: bool
    orchestrator: AgentChoice  # whose model reviews the seams
    deadline_s: float = Field(gt=0)  # the whole pass
    max_cost_usd: float = Field(gt=0)  # the whole map
    expected_seconds_per_chunk: float = Field(ge=0)
    expected_cost_per_chunk_usd: float = Field(ge=0)
    estimate: bool = True  # true until a measured run replaces the figures


class ReviewSettings(BaseModel):
    """The orchestrator model's seam review: strip width, limits, expected figures."""

    strip_squares: float = Field(gt=0)
    max_turns: int = Field(gt=0)
    max_views: int = Field(ge=0)
    max_submissions: int = Field(gt=0)
    max_cost_usd: float = Field(gt=0)
    expected_seconds: dict[AgentChoice, float]  # keyed by orchestrator choice
    expected_cost_usd: dict[AgentChoice, float]


class MergeSettings(BaseModel):
    """The rule-based merge's distances, in squares."""

    join_tolerance_squares: float = Field(gt=0)
    min_piece_squares: float = Field(ge=0)


class ChunkedSettings(BaseModel):
    """The chunked pass: layout, agents, limits, review and merge (`[chunked]`)."""

    default_agents: AgentChoice
    overlap_squares: float = Field(ge=0)
    max_per_side: int = Field(ge=1, le=4)  # at most 4 x 4 = 16 chunks (spec FR-003)
    max_parallel: int = Field(ge=1)
    agents: dict[AgentChoice, AgentSettings]
    limits: Limits
    review: ReviewSettings
    merge: MergeSettings

    @model_validator(mode="after")
    def _check(self) -> "ChunkedSettings":
        """All three choices exist, each orchestrator names one of them and has review
        figures, and the overlap is less than half of every model's part size."""
        missing = [a for a in ("haiku", "sonnet", "opus") if a not in self.agents]
        if missing:
            raise ValueError(f"[chunked.agents] is missing {', '.join(missing)}")
        for choice, agent in self.agents.items():
            if agent.orchestrator not in self.agents:
                raise ValueError(
                    f"{choice!r} names orchestrator {agent.orchestrator!r}, not a choice"
                )
            if agent.orchestrator not in self.review.expected_seconds:
                raise ValueError(
                    f"[chunked.review] has no figures for orchestrator {agent.orchestrator!r}"
                )
        for choice, agent in self.agents.items():
            if not self.overlap_squares < agent.core_squares / 2:
                raise ValueError(
                    f"[chunked] overlap_squares must be less than half of {choice}'s core_squares"
                )
        return self

    def layout(self, map_size: tuple[int, int], agents: str) -> list[Chunk]:
        """The parts of a map of `map_size` squares for the `agents` choice's part size."""
        core = self.agents[agents].core_squares
        return chunk_layout(map_size, core, self.overlap_squares, self.max_per_side)

    def _figures(
        self, n: int, agents: str, detect: bool, size_step: SizeStep
    ) -> tuple[float, float]:
        """Expected (seconds, cost) for `n` chunks with the `agents` choice."""
        agent = self.agents[agents]
        seconds = math.ceil(n / self.max_parallel) * agent.expected_seconds_per_chunk
        cost = n * agent.expected_cost_per_chunk_usd
        if n > 1:
            seconds += self.review.expected_seconds[agent.orchestrator]
            cost += self.review.expected_cost_usd[agent.orchestrator]
        if detect:
            seconds += size_step.expected_seconds
            cost += size_step.expected_cost_usd
        return seconds, cost

    def expected(
        self, map_size: tuple[int, int], agents: str, detect: bool, size_step: SizeStep
    ) -> tuple[float, float]:
        """The button's expected (seconds, cost) for this map size and choice.

        seconds = ceil(n / max_parallel) * per-chunk seconds + review (n > 1) + size step
        (detect); cost = n * per-chunk cost + review (n > 1) + size step (detect).
        """
        return self._figures(len(self.layout(map_size, agents)), agents, detect, size_step)

    def expected_max(self, agents: str, detect: bool, size_step: SizeStep) -> tuple[float, float]:
        """The most a pass can take and cost: the same figures for a full 4 x 4 layout, shown
        when detection may change the chunk count during the pass (spec FR-011)."""
        return self._figures(self.max_per_side**2, agents, detect, size_step)


class Settings(BaseModel):
    """Everything the app reads from the config file."""

    profiles: dict[Literal["quick", "deep"], Profile]
    size_step: SizeStep
    limits: Limits
    views: Views
    prices: dict[str, Price]
    lights: dict[str, LightSpec]
    app: AppLimits
    chunked: ChunkedSettings

    @model_validator(mode="after")
    def _check(self) -> "Settings":
        """Both profiles exist, each profile's model has a price, all three tiers are set, and
        the map-size limits fit the domain's 1..200 (MapSize enforces that range itself)."""
        for kind in ("quick", "deep"):
            if kind not in self.profiles:
                raise ValueError(f"profile {kind!r} is missing")
        for kind, profile in self.profiles.items():
            if profile.name not in self.prices:
                raise ValueError(f"profile {kind!r} uses {profile.name!r}, which has no price")
        for choice, agent in self.chunked.agents.items():
            if agent.name not in self.prices:
                raise ValueError(
                    f"chunked agents {choice!r} use {agent.name!r}, which has no price"
                )
        missing = [t for t in TIERS if t not in self.lights]
        if missing:
            raise ValueError(f"light tiers missing: {', '.join(missing)}")
        app = self.app
        if not MIN_SQUARES <= app.min_squares <= app.max_squares <= MAX_SQUARES:
            raise ValueError(
                f"[app] min_squares..max_squares must lie within {MIN_SQUARES}..{MAX_SQUARES}"
            )
        for side in (app.default_width, app.default_height):
            if not app.min_squares <= side <= app.max_squares:
                raise ValueError("[app] default map size is outside min_squares..max_squares")
        return self

    def light_table(self) -> dict[str, dict]:
        """The light tiers as plain dicts, the form `postprocess.uvtt` takes."""
        return {tier: spec.model_dump() for tier, spec in self.lights.items()}


def load_settings(path: Path = CONFIG) -> Settings:
    """Read and validate the config file; raises pydantic.ValidationError if it is wrong."""
    return Settings.model_validate(tomllib.loads(Path(path).read_text()))
