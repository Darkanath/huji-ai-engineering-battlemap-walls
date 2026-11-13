"""The app's settings, validated from the tracer's config file (`llm/configs/claude.toml`).

The tool loop in `llm/agent.py` reads the same file as a plain dict; this module checks it once
for the app: every profile has a price, every light tier has a range, deadlines are positive.
"""

import tomllib
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, Field, model_validator

from app.domain import MAX_SQUARES, MIN_SQUARES
from llm.agent import CONFIG

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


class SizeStep(BaseModel):
    """Which profile's model works out the map size, in both passes."""

    profile: Literal["quick", "deep"]


class Settings(BaseModel):
    """Everything the app reads from the config file."""

    profiles: dict[Literal["quick", "deep"], Profile]
    size_step: SizeStep
    limits: Limits
    views: Views
    prices: dict[str, Price]
    lights: dict[str, LightSpec]
    app: AppLimits

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
