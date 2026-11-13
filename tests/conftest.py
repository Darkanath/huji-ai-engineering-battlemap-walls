"""Shared fixtures: a small processed dataset built from the demo map, and the scripted fake
model client every tracer and app test uses instead of a paid call."""

import csv
import json
import shutil
from pathlib import Path
from types import SimpleNamespace as NS

import pytest

from data.manifest import build, read_manifest

DEMO_MAP = Path(__file__).parents[1] / "data/raw/dungeondraft/demo-training-map.dd2vtt"
FIXTURES = Path(__file__).parent / "fixtures"


def reply(*blocks, stop: str = "tool_use", model: str = "fake-model") -> NS:
    """A fake API response with 1,000 input and 100 output tokens."""
    usage = NS(
        input_tokens=1000,
        output_tokens=100,
        cache_creation_input_tokens=0,
        cache_read_input_tokens=0,
    )
    return NS(content=list(blocks), stop_reason=stop, usage=usage, model=model)


def call(name: str, args: dict, id_: str = "t1") -> NS:
    """A fake tool_use content block."""
    return NS(type="tool_use", name=name, input=args, id=id_)


def text(body: str) -> NS:
    """A fake text content block."""
    return NS(type="text", text=body)


class FakeClient:
    """Returns the scripted responses in order and records every request.

    A script item that is an exception is raised instead of returned, which is how tests
    produce API errors. The client answers both `client.messages.create` and
    `client.beta.messages.create`, like the real SDK.
    """

    def __init__(self, script):
        """Keep the script and start with no requests."""
        self.script, self.requests = list(script), []
        self.messages = self
        self.beta = NS(messages=self)

    def create(self, **params):
        """Record the request and return (or raise) the next scripted item."""
        self.requests.append({**params, "messages": list(params["messages"])})
        item = self.script.pop(0)
        if isinstance(item, BaseException):
            raise item
        return item


def load_responses(path: Path) -> list[NS]:
    """Recorded model responses from a JSON fixture, as fake API responses.

    Each entry has `stop_reason`, optionally `model`, and `content`: a list of
    `{"type": "text", "text": ...}` or `{"type": "tool_use", "name", "input", "id"}` blocks.
    """

    def block(b: dict) -> NS:
        """One recorded content block as a fake block."""
        if b["type"] == "tool_use":
            return call(b["name"], b["input"], b.get("id", "t1"))
        return text(b["text"])

    return [
        reply(
            *[block(b) for b in r["content"]],
            stop=r["stop_reason"],
            model=r.get("model", "fake-model"),
        )
        for r in json.loads(Path(path).read_text())
    ]


@pytest.fixture(scope="session")
def demo_processed(tmp_path_factory: pytest.TempPathFactory) -> Path:
    """data/processed-style folder with the demo map three times: syn0001 in train, syn0002 in
    val (as a Dungeondraft map, so it counts as real val) and t01 in test."""
    root = tmp_path_factory.mktemp("demo_data")
    raw, processed = root / "raw", root / "processed"
    for dataset, name in (("synthetic", "syn0001"), ("dungeondraft", "dd01_a"), ("test", "t01")):
        (raw / dataset).mkdir(parents=True, exist_ok=True)
        shutil.copy(DEMO_MAP, raw / dataset / f"{name}.dd2vtt")
    build(raw, processed)

    # One map per dataset can't fill every split by itself, so set the splits by hand.
    manifest = processed / "manifest.csv"
    rows = read_manifest(manifest)
    splits = {"syn0001": "train", "dd01_a": "val", "t01": "test"}
    for row in rows:
        row["split"] = splits[row["map"]]
    with open(manifest, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)
    return processed
