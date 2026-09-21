"""Drift: how a recent window of traffic differs from a baseline window, from the event logs.

    python3 -m ops.drift --baseline results/events/week-1.jsonl --recent results/events/week-2.jsonl --out results/drift/week-2.json

The report compares what came in (category mix, request lengths, channels), what the assistant
did with it (routes, escalation reasons, drafted and flagged shares, article choices), how it
performed (latency, tokens per request), and what produced it (versions). Each difference above
a threshold becomes a **signal** of one of three kinds:

- input shift: the customers asked for different things; the versions did not change
- system change: the versions changed, so any difference in behavior may be the system's
- performance: latency or usage moved without a change in mix or versions

A signal is a reason to investigate, never proof that quality fell. Quality is a delayed
measurement made by the recurring evaluation (ops/scheduled_eval.py) on the cases behind the
window; this report says where to look.
"""
import argparse
import json
from collections import Counter
from pathlib import Path

from support_assistant.telemetry.events import read_events
from support_assistant.telemetry.metrics import percentile, summarize

SHARE_POINTS = 0.05      # a share that moves by five points or more is a signal
RATE_POINTS = 0.05
LATENCY_RATIO = 1.5      # p95 that moves by half or more is a signal
MIN_REQUESTS = 50        # below this, shares are too noisy to call


def profile(events: list[dict], input_rate: float | None = None, output_rate: float | None = None) -> dict:
    """Everything the comparison looks at, from one window's events."""
    s = summarize(events, input_rate, output_rate)
    finals = [e for e in events if e["step"] == "request" and e["status"] != "received"]
    received = [e for e in events if e["step"] == "request" and e["status"] == "received"]
    lookups = [e for e in events if e["step"] == "lookup"]
    n = len(finals) or 1
    body_chars = [e["attrs"].get("body", {}).get("chars", 0) for e in received]
    return {
        "requests": len(finals),
        "categories": shares(Counter(e["attrs"].get("category") for e in finals), n),
        "channels": shares(Counter(e["attrs"].get("channel") for e in received), n),
        "body_chars_p50": percentile(body_chars, 50),
        "escalation_rate": s["routes"].get("human_review", 0) / n,
        "drafted_rate": s["drafted"] / n,
        "flagged_rate": s["flagged_drafts"] / n,
        "unavailable_rate": s["model_unavailable"] / n,
        "reasons": shares(Counter(s["reasons"]), n),
        "articles": shares(Counter(e["attrs"].get("article") for e in lookups), n),
        "lookup_method": shares(Counter(e["attrs"].get("method") for e in lookups), len(lookups)) if lookups else {},
        "latency_p50_ms": s["latency_ms"]["p50"],
        "latency_p95_ms": s["latency_ms"]["p95"],
        "tokens_per_request": {"input": s["usage"]["input_tokens"] / n, "output": s["usage"]["output_tokens"] / n},
        "cost_per_request_usd": s["cost"]["per_request_usd"] if s["cost"] else None,
        "versions": s["versions"],
    }


def shares(counter: Counter, total: int) -> dict:
    """Counts as shares of the total, keyed by name; a missing value is named 'none'."""
    return {("none" if k is None else str(k)): v / total for k, v in sorted(counter.items(), key=lambda kv: str(kv[0]))}


def share_deltas(before: dict, after: dict) -> dict:
    keys = sorted(set(before) | set(after), key=str)
    return {str(k): {"before": round(before.get(k, 0.0), 3), "after": round(after.get(k, 0.0), 3), "delta": round(after.get(k, 0.0) - before.get(k, 0.0), 3)} for k in keys}


def compare(baseline: dict, recent: dict) -> dict:
    versions_changed = baseline["versions"] != recent["versions"]
    enough = baseline["requests"] >= MIN_REQUESTS and recent["requests"] >= MIN_REQUESTS
    signals = []

    def add(kind, statement, evidence, caveat):
        signals.append({"kind": kind, "statement": statement, "evidence": evidence, "does_not_prove": caveat})

    if versions_changed:
        add("system_change", "The versions that produced the two windows differ; any behavioral difference below may be the system's, not the customers'.",
            {"baseline": baseline["versions"], "recent": recent["versions"]},
            "that the change made anything worse; the recurring evaluation on the recent cases says that")
    categories = share_deltas(baseline["categories"], recent["categories"])
    for category, row in categories.items():
        if enough and abs(row["delta"]) >= SHARE_POINTS:
            add("system_change" if versions_changed else "input_shift",
                f"The share of {category} requests moved from {row['before']:.0%} to {row['after']:.0%}.",
                {"category": category, **row},
                "that the assistant handles this category worse; it says more of the traffic is this category")
    for name in ("escalation_rate", "drafted_rate", "flagged_rate", "unavailable_rate"):
        delta = recent[name] - baseline[name]
        if enough and abs(delta) >= RATE_POINTS:
            kind = "system_change" if versions_changed else ("input_shift" if any(abs(r["delta"]) >= SHARE_POINTS for r in categories.values()) else "performance")
            add(kind, f"{name.replace('_', ' ')} moved from {baseline[name]:.0%} to {recent[name]:.0%}.",
                {"before": round(baseline[name], 3), "after": round(recent[name], 3), "delta": round(delta, 3)},
                "a fault in the assistant when the category mix also moved; a mix that needs a person more often escalates more often")
    reasons = share_deltas(baseline["reasons"], recent["reasons"])
    for reason, row in reasons.items():
        if enough and abs(row["delta"]) >= RATE_POINTS:
            add("system_change" if versions_changed else "input_shift", f"Escalation reason {reason} moved from {row['before']:.0%} to {row['after']:.0%} of requests.",
                {"reason": reason, **row}, "which requests were mishandled; the reason names the rule, not the customer's need")
    if baseline["latency_p95_ms"] and recent["latency_p95_ms"] and recent["latency_p95_ms"] / baseline["latency_p95_ms"] >= LATENCY_RATIO:
        add("system_change" if versions_changed else "performance", f"Latency p95 moved from {baseline['latency_p95_ms']:.0f} ms to {recent['latency_p95_ms']:.0f} ms.",
            {"before": baseline["latency_p95_ms"], "after": recent["latency_p95_ms"]}, "why: provider, prompt length, or retries; step durations say which")
    if recent["tokens_per_request"]["input"] and baseline["tokens_per_request"]["input"] and abs(recent["tokens_per_request"]["input"] / baseline["tokens_per_request"]["input"] - 1) >= 0.25:
        add("system_change" if versions_changed else "performance", "Input tokens per request moved by a quarter or more.",
            {"before": round(baseline["tokens_per_request"]["input"]), "after": round(recent["tokens_per_request"]["input"])}, "anything about quality; it is a cost signal")
    return {
        "enough_data": enough,
        "versions_changed": versions_changed,
        "categories": categories,
        "reasons": reasons,
        "articles": share_deltas(baseline["articles"], recent["articles"]),
        "rates": {name: {"before": round(baseline[name], 3), "after": round(recent[name], 3)} for name in ("escalation_rate", "drafted_rate", "flagged_rate", "unavailable_rate")},
        "latency_p95_ms": {"before": baseline["latency_p95_ms"], "after": recent["latency_p95_ms"]},
        "tokens_per_request": {"before": baseline["tokens_per_request"], "after": recent["tokens_per_request"]},
        "signals": signals,
        "next_step": ("Run the recurring evaluation on the cases behind the recent window and compare its rubric results with the baseline window's; "
                      "a mix shift with unchanged per-case quality needs knowledge articles, not a rollback; a quality drop with an unchanged mix needs the version history."),
    }


def render(report: dict, baseline: dict, recent: dict) -> str:
    lines = [f"baseline {baseline['requests']} requests, recent {recent['requests']} requests; versions changed: {report['versions_changed']}; enough data: {report['enough_data']}",
             "", "| Category | Baseline share | Recent share | Delta |", "| --- | --- | --- | --- |"]
    for category, row in report["categories"].items():
        lines.append(f"| {category} | {row['before']:.1%} | {row['after']:.1%} | {row['delta']:+.1%} |")
    lines += ["", "| Rate | Baseline | Recent |", "| --- | --- | --- |"]
    for name, row in report["rates"].items():
        lines.append(f"| {name} | {row['before']:.1%} | {row['after']:.1%} |")
    lines.append(f"| latency p95 ms | {report['latency_p95_ms']['before']} | {report['latency_p95_ms']['after']} |")
    lines.append(f"| input tokens per request | {report['tokens_per_request']['before']['input']:.0f} | {report['tokens_per_request']['after']['input']:.0f} |")
    lines += ["", "| Reason | Baseline | Recent | Delta |", "| --- | --- | --- | --- |"]
    for reason, row in report["reasons"].items():
        lines.append(f"| {reason} | {row['before']:.1%} | {row['after']:.1%} | {row['delta']:+.1%} |")
    lines += ["", f"Signals ({len(report['signals'])}):"]
    for signal in report["signals"]:
        lines.append(f"- [{signal['kind']}] {signal['statement']} Does not prove: {signal['does_not_prove']}.")
    lines += ["", "Next: " + report["next_step"]]
    return "\n".join(lines)


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--baseline", required=True)
    parser.add_argument("--recent", required=True)
    parser.add_argument("--input-rate", type=float, default=None)
    parser.add_argument("--output-rate", type=float, default=None)
    parser.add_argument("--out", default=None)
    args = parser.parse_args(argv)
    baseline = profile(read_events(args.baseline), args.input_rate, args.output_rate)
    recent = profile(read_events(args.recent), args.input_rate, args.output_rate)
    report = compare(baseline, recent)
    print(render(report, baseline, recent))
    if args.out:
        Path(args.out).parent.mkdir(parents=True, exist_ok=True)
        Path(args.out).write_text(json.dumps({"baseline": baseline, "recent": recent, "comparison": report}, indent=2) + "\n", encoding="utf-8")
        print(f"\nwrote {args.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
