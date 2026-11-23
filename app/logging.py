"""Structured log lines for the app: one JSON object per line, through the standard library.

Only an allowlist of fields is written (profile, model, timing, tokens, cost, stop reason or
failure kind, map size and its source). The image, the answer's coordinates and the API key
are never logged: unknown fields are dropped, and the key's value is masked in every line as a
last guard.
"""

import json
import logging
import os
import sys

LOGGER = logging.getLogger("battlemap")
ALLOWED = {
    "profile",
    "model",
    "served_by",
    "elapsed_s",
    "input_tokens",
    "output_tokens",
    "cache_write_tokens",
    "cache_read_tokens",
    "turns",
    "views",
    "submissions",
    "cost_usd",
    "stopped",
    "failure",
    "detail",
    "map_size",
    "size_source",
    "walls",
    "portals",
    "lights",
    # The chunked pass (specs/002-chunked-map-tracing/): its parts, merge and seam review.
    "agents",
    "orchestrator",
    "part",
    "window",
    "state",
    "chunks",
    "chunks_failed",
    "chunks_skipped",
    "review",
    "removed",
    "added",
    "joins",
    "ends_snapped",
    "pieces_dropped",
}


def setup_logging(level: int = logging.INFO) -> None:
    """Send the app's log lines to stderr, once; the container's log collects them."""
    if not LOGGER.handlers:
        handler = logging.StreamHandler(sys.stderr)
        handler.setFormatter(logging.Formatter("%(message)s"))
        LOGGER.addHandler(handler)
    LOGGER.setLevel(level)


def format_event(event: str, **fields) -> str:
    """The JSON line for one event, with only allowed fields and the key masked."""
    record = {"event": event, **{k: v for k, v in fields.items() if k in ALLOWED}}
    line = json.dumps(record, default=str)
    key = os.environ.get("ANTHROPIC_API_KEY")
    if key:
        line = line.replace(key, "***")
    return line


def log_event(event: str, **fields) -> None:
    """Write one event as a JSON line to the `battlemap` logger."""
    LOGGER.info(format_event(event, **fields))
