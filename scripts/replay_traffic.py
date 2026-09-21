"""Replay a recorded traffic window through the assistant and write its event log.

    python3 scripts/replay_traffic.py data/traffic/week-1.jsonl --events results/events/week-1.jsonl
    python3 scripts/replay_traffic.py data/traffic/week-1.jsonl --events results/events/week-1-outage.jsonl --outage 60:9
    python3 scripts/replay_traffic.py data/traffic/week-2.jsonl --events results/events/week-2-v2.jsonl --variant v2

The requests run on the replay client, so the drafts and routes are the recorded ones and the
run is free and deterministic. Time is simulated: every event is stamped from the request's
`created_at`, and durations come from a clock that advances by a fixed model latency per call
(`--latency-ms`, default 2400, the live median) plus the retry backoff on failures, so a week of
traffic replays in seconds and the log reads like a week. Failures can be injected at a point in
the window (`--outage START:COUNT` pushes COUNT timeouts before request START) and latency can
be raised for a stretch (`--slow START:END:MS`). The same requests can be replayed under a
different prompt variant to compare two versions on identical traffic.
"""
import argparse
import dataclasses
import hashlib
import json
import sys
from datetime import datetime, timedelta
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from support_assistant.config import load_settings  # noqa: E402
from support_assistant.intake import load_requests  # noqa: E402
from support_assistant.knowledge import load_articles  # noqa: E402
from support_assistant.llm.errors import LLMRateLimited, LLMTimeout, LLMUnavailable  # noqa: E402
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

    The latency is the configured base, spread deterministically by a hash of the prompt (so a
    replay is repeatable and the distribution has a tail), plus a per-output-token term, so a
    long draft takes longer than a short classification, as it does live.
    """

    def __init__(self, inner, clock: SimulatedClock, latency_ms, timeout_seconds: float, flaky=None):
        self.inner = inner
        self.clock = clock
        self.latency_ms = latency_ms      # a callable returning the current latency, or a number
        self.timeout_seconds = timeout_seconds
        self.flaky = flaky                # a callable returning an exception to raise on this call, or None
        self.model = inner.model
        self.calls_seen = 0

    @property
    def usage(self):
        return self.inner.usage

    @property
    def failures(self):
        return self.inner.failures

    def complete(self, system, user, max_tokens):
        base = self.latency_ms() if callable(self.latency_ms) else self.latency_ms
        spread = 0.6 + 0.8 * (int(hashlib.sha256(user.encode("utf-8")).hexdigest()[:8], 16) / 0xFFFFFFFF)
        self.calls_seen += 1
        injected = self.flaky(self.calls_seen) if self.flaky else None
        if injected is not None:
            self.clock.advance(self.timeout_seconds if isinstance(injected, LLMTimeout) else 0.3)
            raise injected
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


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("traffic", help="JSONL requests with created_at, in the order they arrived")
    parser.add_argument("--events", required=True, help="event log to write (overwritten)")
    parser.add_argument("--variant", choices=("v1", "v2"), default=None)
    parser.add_argument("--latency-ms", type=float, default=2400.0, help="simulated model latency per call")
    parser.add_argument("--outage", default=None, help="START:COUNT, inject COUNT timeouts before request index START (1-based)")
    parser.add_argument("--failures", action="append", default=[], help="START:COUNT:KIND, inject COUNT failures of KIND (timeout|rate_limit|unavailable) before request START; repeatable")
    parser.add_argument("--slow", default=None, help="START:END:MS, model latency MS for requests START..END-1 (1-based)")
    parser.add_argument("--rules-from", default=None, help="START:END, process requests START..END-1 in rules mode (the runbook's containment)")
    parser.add_argument("--flaky", default=None, help="START:END:KIND, every other model call fails with KIND for requests START..END-1 and succeeds on retry (an early warning, not an outage)")
    parser.add_argument("--limit", type=int, default=None)
    args = parser.parse_args(argv)

    settings = dataclasses.replace(load_settings(), mode="model", llm_client="replay", events_file=None,
                                   **({"prompt_variant": args.variant} if args.variant else {}))
    clock = SimulatedClock()
    slow = parse_span(args.slow, 3) if args.slow else None
    contain = parse_span(args.rules_from, 2) if args.rules_from else None
    kinds = {"timeout": lambda: LLMTimeout("injected timeout"), "rate_limit": lambda: LLMRateLimited("injected rate limit"),
             "unavailable": lambda: LLMUnavailable("injected outage")}
    injections: dict = {}
    if args.outage:
        start, count = parse_span(args.outage, 2)
        injections.setdefault(start, []).extend(kinds["timeout"]() for _ in range(count))
    for spec in args.failures:
        start, count, kind = spec.split(":")
        injections.setdefault(int(start), []).extend(kinds[kind]() for _ in range(int(count)))
    rules_settings = dataclasses.replace(settings, mode="rules")
    flaky_span = None
    if args.flaky:
        start, end, kind = args.flaky.split(":")
        flaky_span = (int(start), int(end), kinds[kind])

    def flaky(call_number):
        if flaky_span and flaky_span[0] <= current_index["i"] < flaky_span[1] and call_number % 2 == 1:
            return flaky_span[2]()
        return None
    current_index = {"i": 0}

    def latency_now():
        if slow and slow[0] <= current_index["i"] < slow[1]:
            return float(slow[2])
        return args.latency_ms

    replay = build_client(settings)
    client = LatencyClient(replay, clock, latency_now, settings.timeout_seconds, flaky)
    articles = load_articles(settings.knowledge_dir)
    requests = load_requests(args.traffic)
    if args.limit:
        requests = requests[: args.limit]
    events_path = Path(args.events)
    if events_path.exists():
        events_path.unlink()
    sink = EventSink(events_path)

    outcomes = {"draft": 0, "human_review": 0, "unavailable": 0, "rules": 0}
    for index, request in enumerate(requests, start=1):
        current_index["i"] = index
        if index in injections:
            replay.failures.extend(injections[index])
        arrived = datetime.fromisoformat(request.created_at.replace("Z", "+00:00"))
        base = clock.seconds

        def now(arrived=arrived, base=base):
            return (arrived + timedelta(seconds=clock.seconds - base)).isoformat(timespec="milliseconds")

        contained = bool(contain and contain[0] <= index < contain[1])
        active = rules_settings if contained else settings
        result = process_request(request, articles, active, None if contained else client, sleep=clock.advance, sink=sink, clock=clock, now=now)
        outcomes["rules"] += contained
        outcomes[result.route] += 1
        if any(r in ("classification_unavailable", "draft_unavailable") for r in result.reasons):
            outcomes["unavailable"] += 1

    print(f"replayed {len(requests)} requests from {args.traffic} as {settings.prompt_variant}: "
          f"{outcomes['draft']} drafts, {outcomes['human_review']} to a person, {outcomes['unavailable']} with a model step unavailable, "
          f"{outcomes['rules']} handled in rules mode")
    print(f"events: {len(sink)} written to {events_path}")
    print(f"model calls {client.usage.calls}, input tokens {client.usage.input_tokens}, output tokens {client.usage.output_tokens}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
