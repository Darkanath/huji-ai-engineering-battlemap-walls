"""The evaluation command with the fake client: files, summary, cost prompt, resume."""

import csv
import io
import json
import shutil

import anthropic
import pytest

from llm import run
from llm.merge import chunk_layout

from conftest import DEMO_MAP, FakeClient, RoutingFake, call, reply, span, text

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


def test_size_only_runs_one_request_per_map_and_records_it(setup):
    """--size-only asks only for the map size and writes size.json and a summary row."""
    out, client = setup
    run.main([*ARGS, "--yes", "--size-only"])
    assert len(client.requests) == 1
    assert (out / "demo" / "size.json").exists() and not (out / "demo" / "trace.json").exists()
    row = next(csv.DictReader((out / "summary.csv").open()))
    assert row["detected_size"] == "3x3" and row["true_size"] == "25x25"


# --- --chunked (feature 002) -----------------------------------------------------------------


@pytest.fixture
def chunked_setup(tmp_path, monkeypatch):
    """The one-map reference folder and a routing fake: four agents (two trace a wall across
    x = 12.5) and a reviewer that resubmits the wall's strip part."""
    reference = tmp_path / "reference"
    reference.mkdir()
    shutil.copy(DEMO_MAP, reference / "demo.dd2vtt")
    monkeypatch.setattr(run, "REFERENCE", reference)
    monkeypatch.setattr(run, "RUNS", tmp_path / "runs")
    windows = [c.window for c in chunk_layout((25, 25), 13, 1, 4)]

    def submits(tool, walls):
        """A script that submits `walls` with `tool` once and finishes."""
        answer = {"walls": walls, "arcs": [], "portals": [], "lights": []}
        return [reply(call(tool, answer)), reply(text("Done."), stop="end_turn")]

    wall = [{"points": [{"x": 3, "y": 5}, {"x": 22, "y": 5}]}]
    client = RoutingFake(
        {
            **{span(w): submits("submit_answer", wall) for w in windows[:2]},
            **{span(w): submits("submit_answer", []) for w in windows[2:]},
            "review": submits(
                "submit_corrections", [{"points": [{"x": 11.5, "y": 5}, {"x": 13.5, "y": 5}]}]
            ),
        }
    )
    monkeypatch.setattr(anthropic, "Anthropic", lambda *a, **k: client)
    return tmp_path / "runs" / "c", client


CHUNKED_ARGS = ["--reference", "--chunked", "--agents", "sonnet", "--run", "c"]


def test_chunked_run_writes_every_file_and_both_score_sets(chunked_setup):
    """Per map: merged and final answers, the file, the merge and review records, and each
    chunk's folder; the summary has both score sets and the seam checks."""
    out, client = chunked_setup
    run.main([*CHUNKED_ARGS, "--yes"])
    demo = out / "demo"
    for name in (
        "merged.json",
        "answer.json",
        "demo.dd2vtt",
        "preview.jpg",
        "trace.json",
        "merge.json",
        "review/trace.json",
        "review/responses.json",
        "review/submission.json",
    ):
        assert (demo / name).exists(), name
    for i in range(4):
        assert (demo / "chunks" / str(i) / "trace.json").exists()
        assert any((demo / "chunks" / str(i) / "views").glob("*.jpg"))
    assert (demo / "chunks" / "0" / "answer.json").exists()
    row = next(csv.DictReader((out / "summary.csv").open()))
    assert row["method"] == "chunked" and row["agents"] == "sonnet"
    assert row["orchestrator"] == "claude-sonnet-5-5" and row["chunks"] == "4"
    assert row["chunks_failed"] == "0" and row["chunks_skipped"] == "0"
    assert row["review"] == "done" and float(row["review_cost_usd"]) > 0
    for name in (
        "boundary_f1_wall",
        "portal_recall",
        "seam_gap_ends",
        "duplicate_portals",
        "duplicate_lights",
    ):
        assert row[name] != "" and row[f"merged_{name}"] != "", name


def test_chunked_estimate_is_chunks_times_cost_plus_review(chunked_setup, monkeypatch, capsys):
    """Without --yes the prompt states 4 x $0.04 + $0.07 = $0.23 for the map; "n" sends
    nothing."""
    out, client = chunked_setup
    monkeypatch.setattr("sys.stdin", io.StringIO("n\n"))
    run.main(CHUNKED_ARGS)
    printed = capsys.readouterr().out
    assert "estimated cost about $0.23" in printed
    assert "4 chunks" in printed and "$0.04 per chunk" in printed
    assert client.requests == {} and not out.exists()


def test_chunked_map_is_skipped_without_redo(chunked_setup):
    """A second chunked run in the same folder does not pay again."""
    out, client = chunked_setup
    run.main([*CHUNKED_ARGS, "--yes"])
    sent = sum(len(v) for v in client.requests.values())
    run.main([*CHUNKED_ARGS, "--yes"])
    assert sum(len(v) for v in client.requests.values()) == sent
