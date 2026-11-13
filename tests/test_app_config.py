"""The app's settings: the shipped config loads, and a broken one is caught."""

import tomllib

import pytest
from pydantic import ValidationError

from app.config import Settings, load_settings
from data.rasterize import LIGHT_TIERS
from llm.agent import CONFIG


@pytest.fixture
def raw() -> dict:
    """The shipped config file as a dict, for tests to break one field at a time."""
    return tomllib.loads(CONFIG.read_text())


def test_shipped_config_loads():
    """The real config validates and has both profiles."""
    settings = load_settings()
    assert settings.profiles["quick"].name == "claude-sonnet-5-5"
    assert settings.profiles["deep"].name == "claude-opus-5-5"
    assert settings.app.export_ppg == 70


def test_profile_without_a_price_fails(raw):
    """A profile whose model has no price entry is rejected."""
    raw["profiles"]["quick"]["name"] = "claude-unknown"
    with pytest.raises(ValidationError, match="no price"):
        Settings.model_validate(raw)


def test_missing_light_tier_fails(raw):
    """All three light tiers must be present."""
    del raw["lights"]["medium"]
    with pytest.raises(ValidationError, match="medium"):
        Settings.model_validate(raw)


def test_zero_deadline_fails(raw):
    """A pass deadline must be positive."""
    raw["profiles"]["deep"]["deadline_s"] = 0
    with pytest.raises(ValidationError):
        Settings.model_validate(raw)


def test_light_table_matches_the_label_reader():
    """The export's light ranges equal the tiers the label reader uses."""
    lights = load_settings().lights
    assert {t: s.range for t, s in lights.items()} == {
        t: v["range"] for t, v in LIGHT_TIERS.items()
    }


def test_size_step_uses_the_deep_profile():
    """The map-size step is configured to run on the deep profile (Opus) in both passes."""
    assert load_settings().size_step.profile == "deep"


def test_unknown_size_step_profile_fails(raw):
    """The size step must name one of the two profiles."""
    raw["size_step"]["profile"] = "fastest"
    with pytest.raises(ValidationError):
        Settings.model_validate(raw)
