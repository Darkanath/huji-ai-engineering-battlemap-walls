"""The evaluation command with the fake client: files, summary, cost prompt, resume."""

import csv
import io
import json
import shutil

import anthropic
import pytest

from llm import run

from conftest import DEMO_MAP, FakeClient, call, reply, text

ANSWER = {
    "walls": [{"points": [{"x": 1, "y": 1}, {"x": 9, "y": 1}]}],
    "arcs": [],
    "portals": [{"x1": 4, "y1": 3, "x2": 5, "y2": 3}],
    "lights": [],
}


@pytest.fixture
def setup(tmp_path, monkeypatch):
    """A one-map reference folder, a temp run folder, and a fake client that counts requests."""
    reference = tmp_path / "reference"
    reference.mkdir()
    shutil.copy(DEMO_MAP, reference / "demo.dd2vtt")
    monkeypatch.setattr(run, "REFERENCE", reference)
    monkeypatch.setattr(run, "RUNS", tmp_path / "runs")
    client = FakeClient(
        [
            reply(call("report_map_size", {"grid_found": True, "width": 3, "height": 3})),
            reply(call("submit_answer", ANSWER)),
            reply(text("Done."), stop="end_turn"),
        ]
    )
    monkeypatch.setattr(anthropic, "Anthropic", lambda *a, **k: client)
    return tmp_path / "runs" / "t", client


ARGS = ["--reference", "--profile", "deep", "--run", "t"]


def test_reference_run_writes_every_file_and_a_scored_row(setup):
    """One map: all per-map files, and a summary row with profile, sizes and portal recall."""
    out, client = setup
    run.main([*ARGS, "--yes", "--detect-size"])
    for name in ("responses.json", "trace.json", "answer.json", "demo.dd2vtt", "preview.jpg"):
        assert (out / "demo" / name).exists(), name
    row = next(csv.DictReader((out / "summary.csv").open()))
    assert row["profile"] == "deep" and row["model"] == "claude-opus-5-5"
    assert row["detected_size"] == "3x3" and row["size_right"] == "False"
    assert 0 <= float(row["portal_recall"]) <= 1 and row["boundary_f1_wall"]
    assert len(client.requests) == 3
    assert [r["model"] for r in client.requests] == ["claude-opus-5-5"] * 3
    assert float(row["size_cost_usd"]) > 0


def test_responses_hold_no_image_data(setup):
    """responses.json keeps text and tool calls only."""
    out, _ = setup
    run.main([*ARGS, "--yes"])
    raw = (out / "demo" / "responses.json").read_text()
    assert "base64" not in raw and len(raw) < 5000
    names = [b.get("name") for r in json.loads(raw) for b in r["content"]]
    assert "submit_answer" in names


def test_no_at_the_prompt_sends_nothing(setup, monkeypatch, capsys):
    """Without --yes, answering "n" stops before any request."""
    out, client = setup
    monkeypatch.setattr("sys.stdin", io.StringIO("n\n"))
    run.main(ARGS)
    assert client.requests == [] and not (out / "summary.csv").exists()
    assert "estimated cost about $0.32" in capsys.readouterr().out


def test_traced_map_is_skipped_without_redo(setup):
    """A second run in the same folder does not pay for the same map again."""
    out, client = setup
    run.main([*ARGS, "--yes"])
    sent = len(client.requests)
    run.main([*ARGS, "--yes"])
    assert len(client.requests) == sent


def test_estimate_follows_a_model_override(setup, monkeypatch, capsys):
    """With --model, the printed estimate is scaled to that model's price, with a note."""
    monkeypatch.setattr("sys.stdin", io.StringIO("n\n"))
    run.main([*ARGS, "--model", "claude-fable-5-2"])
    out = capsys.readouterr().out
    assert "about $0.64" in out  # $0.32 x (40 / 20), Fable's output price over Opus's
    assert "effort changes are not included" in out
