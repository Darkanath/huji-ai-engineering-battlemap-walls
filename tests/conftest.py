"""Shared test helpers: the demo map's path, and the scripted fake model client every tracer
and app test uses instead of a paid call."""

import json
import threading
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


def span(box) -> str:
    """ "x 0 to 13.5, y 0 to 13.5": how a chunk agent's intro names its window."""
    return f"x {box[0]:g} to {box[2]:g}, y {box[1]:g} to {box[3]:g}"


class RoutingFake:
    """A fake client for the chunked pass, safe to call from several threads.

    Agents run at the same time, so one shared script would be consumed in an unpredictable
    order. Here each agent has its own script, picked by the window its first request names
    ("Your part is x 0 to 13.5, …"), and the seam review has the script under "review".
    A conversation keeps its route for every later request. Missing routes answer with an
    empty finish, so a test only scripts the agents it cares about. `requests` keeps every
    request per route. `FakeClient` is unchanged.
    """

    def __init__(self, routes: dict):
        """`routes` maps a window span (see `span`) or "review" to a list of responses."""
        self.routes = {key: list(script) for key, script in routes.items()}
        self.requests: dict[str, list[dict]] = {}
        self.lock = threading.Lock()
        self.messages = self
        self.beta = NS(messages=self)

    def route(self, params: dict) -> str:
        """Which script a request belongs to."""
        from llm.review import REVIEW_SYSTEM

        if params["system"] == REVIEW_SYSTEM:
            return "review"
        first = params["messages"][0]["content"]
        for block in first:
            if block.get("type") == "text" and "Your part is " in block["text"]:
                return block["text"].split("Your part is ")[1].split(". ")[0]
        return "other"

    def create(self, **params):
        """Record the request under its route and return (or raise) that route's next item."""
        key = self.route(params)
        with self.lock:
            self.requests.setdefault(key, []).append(
                {**params, "messages": list(params["messages"])}
            )
            script = self.routes.get(key)
            item = script.pop(0) if script else reply(text("Nothing to add."), stop="end_turn")
        if isinstance(item, BaseException):
            raise item
        return item
