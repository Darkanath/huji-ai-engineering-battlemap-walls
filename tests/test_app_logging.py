"""Structured logging: one JSON line per event, never the image or the key."""

import json
import logging

from app.logging import log_event


def lines(caplog) -> list[dict]:
    """The `battlemap` logger's records as parsed JSON."""
    return [json.loads(r.getMessage()) for r in caplog.records if r.name == "battlemap"]


def test_event_is_one_json_line_with_its_fields(caplog):
    """A logged event parses back with the given fields."""
    with caplog.at_level(logging.INFO, logger="battlemap"):
        log_event("pass_finished", profile="quick", cost_usd=0.07, turns=3)
    assert lines(caplog) == [
        {"event": "pass_finished", "profile": "quick", "cost_usd": 0.07, "turns": 3}
    ]


def test_forbidden_fields_are_dropped(caplog):
    """Fields named api_key, key, image or answer never reach the log."""
    with caplog.at_level(logging.INFO, logger="battlemap"):
        log_event("x", api_key="k", key="k", image="data", answer={"walls": []}, profile="deep")
    assert lines(caplog) == [{"event": "x", "profile": "deep"}]


def test_the_key_value_never_appears(caplog, monkeypatch):
    """Even inside an allowed field, the key's value is masked."""
    secret = "sk-ant-test-0123456789"
    monkeypatch.setenv("ANTHROPIC_API_KEY", secret)
    with caplog.at_level(logging.INFO, logger="battlemap"):
        log_event("pass_failed", detail=f"bad key {secret}")
    assert all(secret not in r.getMessage() for r in caplog.records)
