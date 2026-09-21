"""A trace ties every step of one request together and times each one.

The clock is injected so tests never wait and so durations can be asserted exactly. A metered
client wraps the model client for the duration of one request and attributes each completion's
tokens to the step that made the call, which stays correct when requests run concurrently.
"""
import time
import uuid
from contextlib import contextmanager
from dataclasses import dataclass, field

from ..llm.client import Completion, UsageTotals
from .events import Event, EventSink, now_iso


@dataclass
class StepUsage:
    calls: int = 0
    input_tokens: int = 0
    output_tokens: int = 0

    def add(self, completion: Completion) -> None:
        self.calls += 1
        self.input_tokens += completion.input_tokens
        self.output_tokens += completion.output_tokens

    def as_attrs(self) -> dict:
        return {"calls": self.calls, "input_tokens": self.input_tokens, "output_tokens": self.output_tokens}


class MeteredClient:
    """Forwards to the real client and attributes token usage to the trace's current step."""

    def __init__(self, inner, trace: "Trace"):
        self.inner = inner
        self.trace = trace
        self.model = getattr(inner, "model", None)

    @property
    def usage(self) -> UsageTotals:
        return self.inner.usage

    def complete(self, system: str, user: str, max_tokens: int) -> Completion:
        completion = self.inner.complete(system, user, max_tokens)
        self.trace.record_usage(completion)
        return completion


@dataclass
class Trace:
    request_id: str
    sink: EventSink
    clock: callable = time.perf_counter
    trace_id: str = field(default_factory=lambda: uuid.uuid4().hex[:16])
    started: float | None = None
    current_step: str | None = None
    usage: dict = field(default_factory=dict)          # step -> StepUsage
    total_usage: StepUsage = field(default_factory=StepUsage)

    def __post_init__(self):
        self.started = self.clock()

    def emit(self, step: str, status: str, duration_ms: float | None = None, **attrs) -> Event:
        event = Event(ts=now_iso(), trace_id=self.trace_id, request_id=self.request_id, step=step,
                      status=status, duration_ms=None if duration_ms is None else round(duration_ms, 1), attrs=attrs)
        self.sink.emit(event)
        return event

    def record_usage(self, completion: Completion) -> None:
        step = self.current_step or "unattributed"
        self.usage.setdefault(step, StepUsage()).add(completion)
        self.total_usage.add(completion)

    def meter(self, client):
        return None if client is None else MeteredClient(client, self)

    @contextmanager
    def step(self, name: str, **attrs):
        """Time a step. The body sets `outcome.status` and may add attrs; an exception is 'failed'."""
        outcome = StepOutcome()
        self.current_step = name
        begin = self.clock()
        try:
            yield outcome
        except Exception as error:
            outcome.status = "failed"
            outcome.attrs["error"] = type(error).__name__
            raise
        finally:
            elapsed_ms = (self.clock() - begin) * 1000
            usage = self.usage.get(name)
            merged = dict(attrs, **outcome.attrs)
            if usage:
                merged.update(usage.as_attrs())
            self.current_step = None
            self.emit(name, outcome.status, elapsed_ms, **merged)

    def elapsed_ms(self) -> float:
        return (self.clock() - self.started) * 1000


@dataclass
class StepOutcome:
    status: str = "ok"
    attrs: dict = field(default_factory=dict)
