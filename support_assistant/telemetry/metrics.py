"""Measurements over an event log: latency, errors, usage, estimated cost, and routing counts.

Everything here is recomputed from events, so a report cannot say what the log does not.
Cost needs rates the operator supplies (dollars per million input and output tokens); with no
rates, cost is reported as not computed, never guessed.

    python3 -m support_assistant.telemetry.metrics results/events/batch.jsonl --input-rate 1.00 --output-rate 5.00
"""
import argparse
import json
from collections import Counter, defaultdict
from pathlib import Path

from .events import read_events


def percentile(values: list[float], p: float) -> float | None:
    if not values:
        return None
    ordered = sorted(values)
    index = min(len(ordered) - 1, max(0, round(p / 100 * (len(ordered) - 1))))
    return ordered[index]


def estimate_cost(input_tokens: int, output_tokens: int, input_rate: float | None, output_rate: float | None) -> float | None:
    """Dollars, from tokens and explicit dollars-per-million rates; None when a rate is missing."""
    if input_rate is None or output_rate is None:
        return None
    return round(input_tokens / 1e6 * input_rate + output_tokens / 1e6 * output_rate, 6)


def summarize(events: list[dict], input_rate: float | None = None, output_rate: float | None = None) -> dict:
    by_trace: dict = defaultdict(list)
    for event in events:
        by_trace[event["trace_id"]].append(event)
    # The final "request" event of each trace; the "received" event only marks the start.
    requests = [e for e in events if e["step"] == "request" and e["status"] != "received"]
    completed = [e for e in requests if e["status"] in ("ok", "escalated", "flagged")]
    failed = [e for e in requests if e["status"] == "failed"]
    durations = [e["duration_ms"] for e in requests if e.get("duration_ms") is not None]
    steps = [e for e in events if e["step"] != "request"]
    step_status = Counter((e["step"], e["status"]) for e in steps)
    step_durations: dict = defaultdict(list)
    for e in steps:
        if e.get("duration_ms") is not None:
            step_durations[e["step"]].append(e["duration_ms"])
    input_tokens = sum(e["attrs"].get("input_tokens", 0) for e in steps)
    output_tokens = sum(e["attrs"].get("output_tokens", 0) for e in steps)
    calls = sum(e["attrs"].get("calls", 0) for e in steps)
    routes = Counter(e["attrs"].get("route") for e in requests if e["attrs"].get("route"))
    reasons = Counter(r for e in requests for r in e["attrs"].get("reasons", []))
    categories = Counter(e["attrs"].get("category") for e in requests if e["attrs"].get("category"))
    versions = Counter(json.dumps(e["attrs"].get("versions"), sort_keys=True) for e in requests if e["attrs"].get("versions"))
    model_failures = sum(e["attrs"].get("failed_calls", 0) for e in steps)          # every attempt that raised, retried or not
    # Completed after at least one failed attempt: the model answered on a retry.
    retried_requests = sum(1 for e in requests if e["attrs"].get("failed_calls", 0) > 0
                           and not any(r in ("classification_unavailable", "draft_unavailable") for r in e["attrs"].get("reasons", [])))
    unavailable = sum(1 for e in requests if any(r in ("classification_unavailable", "draft_unavailable") for r in e["attrs"].get("reasons", [])))
    cost = estimate_cost(input_tokens, output_tokens, input_rate, output_rate)
    return {
        "requests": len(requests),
        "traces": len(by_trace),
        "completed": len(completed),
        "failed": len(failed),
        "model_unavailable": unavailable,
        "latency_ms": {"p50": percentile(durations, 50), "p95": percentile(durations, 95), "max": max(durations) if durations else None},
        "step_latency_ms_p50": {step: percentile(values, 50) for step, values in sorted(step_durations.items())},
        "step_status": {f"{step}:{status}": n for (step, status), n in sorted(step_status.items())},
        "model_call_failures": model_failures,
        "requests_with_retries": retried_requests,
        "usage": {"calls": calls, "input_tokens": input_tokens, "output_tokens": output_tokens},
        "cost": None if cost is None else {"total_usd": cost, "per_request_usd": round(cost / len(requests), 6) if requests else None,
                                           "input_rate_per_million": input_rate, "output_rate_per_million": output_rate},
        "routes": dict(routes),
        "reasons": dict(reasons),
        "categories": dict(categories),
        "drafted": sum(1 for e in requests if e["attrs"].get("drafted")),
        "flagged_drafts": sum(1 for e in requests if e["status"] == "flagged"),
        "versions": [json.loads(v) for v in versions],
    }


def render(summary: dict) -> str:
    lat = summary["latency_ms"]
    lines = [
        f"requests {summary['requests']}  completed {summary['completed']}  failed {summary['failed']}  model unavailable {summary['model_unavailable']}",
        f"latency ms  p50 {lat['p50']}  p95 {lat['p95']}  max {lat['max']}",
        "step p50 ms  " + "  ".join(f"{s} {v}" for s, v in summary["step_latency_ms_p50"].items()),
        f"model calls {summary['usage']['calls']}  input tokens {summary['usage']['input_tokens']}  output tokens {summary['usage']['output_tokens']}  call failures {summary['model_call_failures']}",
    ]
    cost = summary["cost"]
    lines.append("cost  not computed (pass --input-rate and --output-rate)" if cost is None else
                 f"cost  ${cost['total_usd']:.4f} total  ${cost['per_request_usd']:.5f} per request  at {cost['input_rate_per_million']}/{cost['output_rate_per_million']} per million tokens")
    lines.append("routes  " + "  ".join(f"{k} {v}" for k, v in sorted(summary["routes"].items())) + f"  drafted {summary['drafted']}  flagged {summary['flagged_drafts']}")
    lines.append("reasons  " + ("  ".join(f"{k} {v}" for k, v in sorted(summary["reasons"].items())) or "none"))
    lines.append("versions  " + "; ".join(json.dumps(v, sort_keys=True) for v in summary["versions"]))
    return "\n".join(lines)


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("events", help="JSONL event log")
    parser.add_argument("--input-rate", type=float, default=None, help="dollars per million input tokens")
    parser.add_argument("--output-rate", type=float, default=None, help="dollars per million output tokens")
    parser.add_argument("--json", action="store_true", help="print the summary as JSON")
    args = parser.parse_args(argv)
    summary = summarize(read_events(args.events), args.input_rate, args.output_rate)
    print(json.dumps(summary, indent=2) if args.json else render(summary))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
