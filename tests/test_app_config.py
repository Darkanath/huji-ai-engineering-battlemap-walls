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


def test_map_size_limits_outside_the_domain_fail(raw):
    """[app] max_squares above 200 is refused, since MapSize allows only 1..200."""
    raw["app"]["max_squares"] = 300
    with pytest.raises(ValidationError, match="min_squares"):
        Settings.model_validate(raw)


def test_default_size_outside_the_limits_fails(raw):
    """The default map size must be inside min_squares..max_squares."""
    raw["app"]["default_width"] = 250
    with pytest.raises(ValidationError, match="default"):
        Settings.model_validate(raw)


# --- The chunked pass's settings (feature 002) -----------------------------------------------


def test_shipped_chunked_settings_load():
    """All three agent choices load, paired with their orchestrators, Sonnet by default."""
    chunked = load_settings().chunked
    assert set(chunked.agents) == {"haiku", "sonnet", "opus"}
    assert chunked.default_agents == "sonnet"
    assert [chunked.agents[a].orchestrator for a in ("haiku", "sonnet", "opus")] == [
        "sonnet",
        "sonnet",
        "opus",
    ]
    # Sonnet and Haiku were measured on 23.11; Opus is still an estimate.
    assert [chunked.agents[a].estimate for a in ("haiku", "sonnet", "opus")] == [
        False,
        False,
        True,
    ]


@pytest.mark.parametrize(
    ("change", "message"),
    [
        (lambda c: c["agents"].pop("haiku"), "haiku"),
        (lambda c: c["agents"]["opus"].update(orchestrator="fable"), "orchestrator"),
        (lambda c: c["agents"]["haiku"].update(name="claude-unknown"), "no price"),
        (lambda c: c.update(max_per_side=5), "max_per_side"),
        (lambda c: c["agents"]["haiku"].update(core_squares=2), "overlap"),
        (lambda c: c["agents"]["sonnet"].update(core_squares=1), "core_squares"),
    ],
    ids=["missing-choice", "bad-orchestrator", "no-price", "too-many", "overlap", "tiny-core"],
)
def test_broken_chunked_settings_fail(raw, change, message):
    """A missing choice, an orchestrator that names no entry, an unpriced model, more than 4
    per side, an overlap of half a core or more, or a core under 2 squares is rejected."""
    change(raw["chunked"])
    with pytest.raises(ValidationError, match=message):
        Settings.model_validate(raw)


def test_expected_figures_follow_the_map_size_choice_and_detection():
    """seconds = ceil(n / parallel) * per chunk + review (n > 1) + size step (detect);
    cost = n * per chunk + review (n > 1) + size step (detect)."""
    settings = load_settings()
    chunked = settings.chunked
    seconds, cost = chunked.expected((25, 25), "sonnet", detect=False, size_step=settings.size_step)
    assert seconds == pytest.approx(35) and cost == pytest.approx(0.23)
    seconds, cost = chunked.expected((25, 25), "sonnet", detect=True, size_step=settings.size_step)
    assert seconds == pytest.approx(43) and cost == pytest.approx(0.26)
    seconds, cost = chunked.expected((13, 13), "sonnet", detect=False, size_step=settings.size_step)
    assert seconds == pytest.approx(17) and cost == pytest.approx(0.04)  # one chunk, no review
    _, cost = chunked.expected((50, 50), "opus", detect=False, size_step=settings.size_step)
    assert len(chunked.layout((50, 50), "opus")) == 16 and cost == pytest.approx(3.35)


def test_each_model_has_its_own_part_size():
    """Haiku gets smaller parts (about 7 squares: 16 on 25 x 25) than Sonnet and Opus (13:
    4 on 25 x 25); every model keeps the 16-part cap and 4 agents at a time."""
    settings = load_settings()
    chunked = settings.chunked
    assert [chunked.agents[a].core_squares for a in ("haiku", "sonnet", "opus")] == [7, 13, 13]
    assert len(chunked.layout((25, 25), "haiku")) == 16
    assert len(chunked.layout((25, 25), "sonnet")) == 4
    assert len(chunked.layout((200, 200), "haiku")) == 16
    seconds, cost = chunked.expected((25, 25), "haiku", detect=False, size_step=settings.size_step)
    assert seconds == pytest.approx(98) and cost == pytest.approx(0.1228)


def test_expected_max_is_the_four_by_four_layout():
    """The upper bound shown when detection may change the chunk count (FR-011)."""
    settings = load_settings()
    seconds, cost = settings.chunked.expected_max(
        "sonnet", detect=True, size_step=settings.size_step
    )
    assert seconds == pytest.approx(94) and cost == pytest.approx(0.74)
