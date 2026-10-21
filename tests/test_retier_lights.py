"""Tests for data/retier_lights.py: mapping other tools' lights to the project's tiers."""

import json
from pathlib import Path

import pytest

from data.rasterize import LIGHT_TIERS, load_uvtt, parse_lights
from data.retier_lights import DEFAULT_CONFIG, load_rules, main, retier

RULES = [
    {"range": 4.0, "intensity": 3.0, "tier": "small", "what": "sconce"},
    {"range": 10.0, "intensity": 3.0, "tier": "medium", "what": "fireplace"},
    {"range": 6.0, "intensity": 1.0, "tier": "drop", "what": "crystal"},
]


def make_light(x: float, y: float, light_range: float, intensity: float) -> dict:
    """A light as Dungeon Alchemist exports it."""
    return {
        "position": {"x": x, "y": y},
        "range": light_range,
        "intensity": intensity,
        "color": "ffFFEBBF",
        "shadows": True,
    }


def make_uvtt(lights: list[dict]) -> dict:
    """A minimal 4x4-square .dd2vtt (no image needed for retiering) with the given lights."""
    return {
        "format": 0.2,
        "resolution": {"map_origin": {"x": 0, "y": 0}, "map_size": {"x": 4, "y": 4}},
        "line_of_sight": [[{"x": 0, "y": 2}, {"x": 4, "y": 2}]],
        "portals": [],
        "lights": lights,
    }


def test_ranges_become_tier_ranges() -> None:
    """Matched lights get their tier's range; position and everything else are kept."""
    uvtt = make_uvtt([make_light(1, 1, 4.0, 3.0), make_light(3, 3, 10.0, 3.0)])
    out, counts = retier(uvtt, RULES)
    assert [light["range"] for light in out["lights"]] == [
        LIGHT_TIERS["small"]["range"],
        LIGHT_TIERS["medium"]["range"],
    ]
    assert out["lights"][0]["position"] == {"x": 1, "y": 1}
    assert out["line_of_sight"] == uvtt["line_of_sight"]
    assert counts == {"sconce -> small": 1, "fireplace -> medium": 1}
    # The rasterizer now accepts the file and reads the intended tiers back.
    assert [tier for _, _, tier in parse_lights(out)] == ["small", "medium"]


def test_input_is_not_modified() -> None:
    """retier returns a copy; the original export's lights keep their ranges."""
    uvtt = make_uvtt([make_light(1, 1, 4.0, 3.0)])
    retier(uvtt, RULES)
    assert uvtt["lights"][0]["range"] == 4.0


def test_drop_rule_removes_light() -> None:
    """Lights from things that are not light sources by the rules are removed."""
    out, counts = retier(make_uvtt([make_light(1, 1, 6.0, 1.0)]), RULES)
    assert out["lights"] == []
    assert counts == {"crystal -> drop": 1}


def test_unknown_lights_are_all_listed() -> None:
    """Every unmatched light is reported (range, intensity, position), not just the first."""
    uvtt = make_uvtt([make_light(1, 1, 7.0, 2.0), make_light(2, 2, 4.0, 1.5)])
    with pytest.raises(ValueError) as err:
        retier(uvtt, RULES)
    assert "range 7, intensity 2 at (1.00, 1.00)" in str(err.value)
    assert "range 4, intensity 1.5 at (2.00, 2.00)" in str(err.value)


def test_shipped_config_is_valid() -> None:
    """The Dungeon Alchemist rules in the config load and name only known tiers."""
    rules = load_rules("dungeon_alchemist", DEFAULT_CONFIG)
    assert rules
    assert all(rule["tier"] in LIGHT_TIERS or rule["tier"] == "drop" for rule in rules)


def test_cli_writes_converted_copy(tmp_path: Path, capsys: pytest.CaptureFixture) -> None:
    """The CLI writes the converted file to --out and leaves the original untouched."""
    original = tmp_path / "original" / "da99_a.dd2vtt"
    original.parent.mkdir()
    original.write_text(json.dumps(make_uvtt([make_light(1, 1, 4.0, 3.0)])), encoding="utf-8")
    config = tmp_path / "rules.toml"
    config.write_text(
        '[test]\nrules = [{ range = 4.0, intensity = 3.0, tier = "small", what = "sconce" }]\n',
        encoding="utf-8",
    )
    main([str(original), "--source", "test", "--out", str(tmp_path), "--config", str(config)])

    assert load_uvtt(tmp_path / "da99_a.dd2vtt")["lights"][0]["range"] == 8.0
    assert load_uvtt(original)["lights"][0]["range"] == 4.0
    assert "1 sconce -> small" in capsys.readouterr().out


def test_refuses_to_overwrite_original(tmp_path: Path) -> None:
    """Writing into the folder the original is in would replace it, so it is refused."""
    original = tmp_path / "da99_a.dd2vtt"
    original.write_text(json.dumps(make_uvtt([])), encoding="utf-8")
    config = tmp_path / "rules.toml"
    config.write_text("[test]\nrules = []\n", encoding="utf-8")
    with pytest.raises(ValueError, match="overwrite itself"):
        main([str(original), "--source", "test", "--out", str(tmp_path), "--config", str(config)])
