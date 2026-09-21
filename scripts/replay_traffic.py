"""Replay a recorded traffic window through the assistant and write its event log.

    python3 scripts/replay_traffic.py data/traffic/week-1.jsonl --events results/events/week-1.jsonl
    python3 scripts/replay_traffic.py data/traffic/week-1.jsonl --events results/events/week-1-outage.jsonl --outage 60:63
    python3 scripts/replay_traffic.py data/traffic/week-2.jsonl --events results/events/week-2-v2.jsonl --variant v2

The requests run on the replay client, so the drafts and routes are the recorded ones and the
run is free and deterministic. Time is simulated: every event is stamped from the request's
`created_at`, and durations come from a clock that advances, per call, by half of `--latency-ms`
(default 2400, the live median for a drafted request) spread between 0.6 and 1.4 by a hash of the
prompt, plus 8 ms per output token, plus the full timeout on a timed-out call and the retry
backoff, so a week of traffic replays in seconds and the log reads like a week. Each trace id is
derived from the request id and the name of the events file, so replaying the same traffic into
a log of the same name reproduces it byte for byte.

Spans name requests by their position in the window (1-based, END excluded). An outage is a
stretch of simulated time, not a number of failed calls: `--outage START:END` times out every
model call made from the arrival of request START until the arrival of request END, whichever
request makes it. Latency can be raised for a stretch of requests (`--slow START:END:MS`). The
same requests can be replayed under a different prompt variant to compare two versions on
identical traffic.
"""
import argparse
import dataclasses
import hashlib
import sys
from datetime import datetime, timedelta
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from support_assistant.config import load_settings  # noqa: E402
from support_assistant.intake import load_requests  # noqa: E402
from support_assistant.knowledge import load_articles  # noqa: E402
from support_assistant.llm.errors import LLMTimeout  # noqa: E402
from support_assistant.llm.factory import build_client  # noqa: E402
from support_assistant.pipeline import process_request  # noqa: E402
from support_assistant.telemetry.events import EventSink  # noqa: E402


class SimulatedClock:
    """A perf-counter stand-in that only moves when told to."""

    def __init__(self):
        self.seconds = 0.0

    def __call__(self):
        return self.seconds

    def advance(self, seconds: float):
        self.seconds += seconds


class LatencyClient:
    """Forwards to the replay client and advances the simulated clock by a plausible model latency.

    The latency is half the configured base, spread deterministically by a hash of the prompt (so a
    replay is repeatable and the distribution has a tail), plus a per-output-token term, so a
    long draft takes longer than a short classification, as it does live.
    """

    def __init__(self, inner, clock: SimulatedClock, latency_ms, timeout_seconds: float, inject=None):
        self.inner = inner
        self.clock = clock
        self.latency_ms = latency_ms      # a callable returning the current latency, or a number
        self.timeout_seconds = timeout_seconds
        self.inject = inject              # a callable returning the failure a call made now meets, or None
        self.model = inner.model

    @property
    def usage(self):
        return self.inner.usage

    @property
    def failures(self):
        return self.inner.failures

    def complete(self, system, user, max_tokens):
        base = self.latency_ms() if callable(self.latency_ms) else self.latency_ms
        spread = 0.6 + 0.8 * (int(hashlib.sha256(user.encode("utf-8")).hexdigest()[:8], 16) / 0xFFFFFFFF)
        failure = self.inject() if self.inject else None      # an outage fails every call made inside it
        if failure is not None:
            self.clock.advance(self.timeout_seconds if isinstance(failure, LLMTimeout) else 0.3)
            raise failure
        try:
            completion = self.inner.complete(system, user, max_tokens)
        except LLMTimeout:
            self.clock.advance(self.timeout_seconds)      # a timeout takes the whole timeout to fail
            raise
        except Exception:
            self.clock.advance(0.3)                       # a rejected call fails fast
            raise
        self.clock.advance((base * 0.5 * spread + completion.output_tokens * 8.0) / 1000)
        return completion


def parse_span(text: str, parts: int) -> tuple:
    values = tuple(int(x) for x in text.split(":"))
    if len(values) != parts:
        raise SystemExit(f"expected {parts} colon-separated integers, got {text!r}")
    return values


def arrival(request) -> datetime:
    return datetime.fromisoformat(request.created_at.replace("Z", "+00:00"))


def time_span(arrivals: list, start: int, end: int) -> tuple:
    """Simulated time from the arrival of request START to the arrival of request END (1-based).
    An END past the window leaves the span open to the end of the replay."""
    if not 1 <= start < end:
        raise SystemExit(f"a span needs 1 <= START < END, got {start}:{end}")
    if start > len(arrivals):
        raise SystemExit(f"span start {start} is past the window ({len(arrivals)} requests)")
    return arrivals[start - 1], (arrivals[end - 1] if end <= len(arrivals) else None)


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("traffic", help="JSONL requests with created_at, in the order they arrived")
    parser.add_argument("--events", required=True, help="event log to write (overwritten)")
    parser.add_argument("--variant", choices=("v1", "v2"), default=None)
    parser.add_argument("--latency-ms", type=float, default=2400.0, help="base latency per call; a call takes half of it, spread by the prompt hash, plus 8 ms per output token")
    parser.add_argument("--outage", default=None, help="START:END, every model call times out from the arrival of request START until the arrival of request END (1-based)")
    parser.add_argument("--slow", default=None, help="START:END:MS, base latency MS for requests START..END-1 (1-based)")
    parser.add_argument("--limit", type=int, default=None)
    args = parser.parse_args(argv)

    settings = dataclasses.replace(load_settings(), mode="model", llm_client="replay", events_file=None,
                                   **({"prompt_variant": args.variant} if args.variant else {}))
    clock = SimulatedClock()
    outages = [(*parse_span(args.outage, 2), lambda: LLMTimeout("injected outage"))] if args.outage else []   # (START, END, error)
    slow = parse_span(args.slow, 3) if args.slow else None
    current_index = {"i": 0}
    current_time = {"at": None}     # a callable giving the simulated time inside the request being replayed
    failures: list = []             # (begin, end or None, error), in simulated time

    def failure_now():
        """The failure the provider gives a call made now: an outage fails every call inside it."""
        moment = current_time["at"]()
        for begin, end, make in failures:
            if begin <= moment and (end is None or moment < end):
                return make()
        return None

    def latency_now():
        if slow and slow[0] <= current_index["i"] < slow[1]:
            return float(slow[2])
        return args.latency_ms

    replay = build_client(settings)
    client = LatencyClient(replay, clock, latency_now, settings.timeout_seconds, inject=failure_now)
    articles = load_articles(settings.knowledge_dir)
    requests = load_requests(args.traffic)
    arrivals = [arrival(r) for r in requests]      # the whole window, so a span can end past --limit
    failures.extend((*time_span(arrivals, start, end), make) for start, end, make in outages)
    if args.limit:
        requests = requests[: args.limit]
    events_path = Path(args.events)
    if events_path.exists():
        events_path.unlink()
    sink = EventSink(events_path)
    label = events_path.stem

    def trace_id_for(request_id: str) -> str:
        """From the log's name and the request: a replay into a log of the same name is reproducible."""
        return hashlib.sha256(f"{label}:{request_id}".encode("utf-8")).hexdigest()[:16]

    outcomes = {"draft": 0, "human_review": 0, "unavailable": 0}
    for index, request in enumerate(requests, start=1):
        current_index["i"] = index
        arrived = arrivals[index - 1]
        base = clock.seconds

        def at(arrived=arrived, base=base):
            return arrived + timedelta(seconds=clock.seconds - base)

        def now(at=at):
            return at().isoformat(timespec="milliseconds")

        current_time["at"] = at
        result = process_request(request, articles, settings, client, sleep=clock.advance, sink=sink, clock=clock, now=now,
                                 trace_id=trace_id_for(request.id))
        outcomes[result.route] += 1
        if any(r in ("classification_unavailable", "draft_unavailable") for r in result.reasons):
            outcomes["unavailable"] += 1

    print(f"replayed {len(requests)} requests from {args.traffic} as {settings.prompt_variant}: "
          f"{outcomes['draft']} drafts, {outcomes['human_review']} to a person, {outcomes['unavailable']} with a model step unavailable")
    print(f"events: {len(sink)} written to {events_path}")
    print(f"model calls {client.usage.calls}, input tokens {client.usage.input_tokens}, output tokens {client.usage.output_tokens}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
