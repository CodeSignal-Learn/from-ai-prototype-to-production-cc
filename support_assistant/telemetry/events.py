"""Structured events: one JSON object per step of one request, written as they happen.

An event says what happened operationally: a step started and ended, how long it took, whether
it succeeded, how many tokens it used, which versions produced it. It never says whether the
draft was any good; that is a claim about semantic quality and belongs to the evaluation suite.
Events carry no customer text and no draft text: request ids, lengths, hashes, categories,
routes, reasons, and counts only, so a log can be kept, shipped, and read without becoming a
second copy of the customers' messages.
"""
import hashlib
import json
import threading
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path

SCHEMA_VERSION = 1


@dataclass(frozen=True)
class Event:
    ts: str                 # ISO 8601, UTC
    trace_id: str           # one per request, shared by every step of it
    request_id: str
    step: str               # request | classify | lookup | draft | checks | route
    status: str             # ok | failed | declined | flagged | escalated | ...
    duration_ms: float | None = None
    attrs: dict = field(default_factory=dict)
    schema: int = SCHEMA_VERSION

    def to_json(self) -> str:
        return json.dumps(asdict(self), ensure_ascii=False, sort_keys=True)


def text_fingerprint(text: str) -> dict:
    """What an event may say about a text: its length and a hash, never the text."""
    return {"chars": len(text), "sha256": hashlib.sha256(text.encode("utf-8")).hexdigest()[:12]}


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="milliseconds")


class EventSink:
    """Where events go. Appends JSON lines to a file, or keeps them in memory when no path is set.

    Thread-safe: the pipeline runs requests concurrently and every request writes its own events.
    """

    def __init__(self, path: str | Path | None = None):
        self.path = Path(path) if path else None
        self.events: list[Event] = []
        self._lock = threading.Lock()
        if self.path:
            self.path.parent.mkdir(parents=True, exist_ok=True)

    def emit(self, event: Event) -> None:
        line = event.to_json()
        with self._lock:
            self.events.append(event)
            if self.path:
                with self.path.open("a", encoding="utf-8") as handle:
                    handle.write(line + "\n")

    def __len__(self) -> int:
        return len(self.events)


def read_events(path: str | Path) -> list[dict]:
    """Load an event log written by EventSink."""
    rows = []
    for line in Path(path).read_text(encoding="utf-8").splitlines():
        if line.strip():
            rows.append(json.loads(line))
    return rows
