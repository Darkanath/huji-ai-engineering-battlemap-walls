"""Shared test helpers: the demo map's path, and the scripted fake model client every tracer
and app test uses instead of a paid call."""

import json
from pathlib import Path
from types import SimpleNamespace as NS

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
