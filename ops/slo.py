"""Service objectives: indicators computed over windows of the event log, compared with targets.

    python3 -m ops.slo results/events/week-1.jsonl --input-rate 1.00 --output-rate 5.00
    python3 -m ops.slo results/events/week-1.jsonl --objectives ops/objectives.json --window-minutes 1440

An indicator is a number recomputed from the events in a window (availability, latency p95,
escalation rate, flagged-draft rate, cost per request). An objective is an indicator, a target,
a comparison, a window length, and the minimum number of requests a window needs before the
number means anything. Objectives are data in ops/objectives.json so the team can change a
target without changing code. Indicators from events are immediate; whether the drafts were
any good is a delayed measurement that comes from the recurring evaluation, not from here.
"""
import argparse
import json
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path

from support_assistant.telemetry.events import read_events
from support_assistant.telemetry.metrics import summarize

OPS_DIR = Path(__file__).resolve().parent
DEFAULT_OBJECTIVES = OPS_DIR / "objectives.json"
COMPARISONS = {"<=": lambda value, target: value <= target, ">=": lambda value, target: value >= target}


@dataclass(frozen=True)
class Objective:
    name: str
    indicator: str
    target: float
    comparison: str          # "<=" or ">="
    window_minutes: int
    min_requests: int
    why: str


def load_objectives(path: Path = DEFAULT_OBJECTIVES) -> list[Objective]:
    rows = json.loads(Path(path).read_text(encoding="utf-8"))
    objectives = []
    for row in rows:
        if row["comparison"] not in COMPARISONS:
            raise ValueError(f"objective {row['name']}: comparison must be <= or >=")
        if row["indicator"] not in INDICATORS:
            raise ValueError(f"objective {row['name']}: unknown indicator {row['indicator']!r}")
        objectives.append(Objective(**row))
    return objectives


def parse_ts(value: str) -> datetime:
    return datetime.fromisoformat(value.replace("Z", "+00:00"))


def windows(events: list[dict], minutes: int) -> list[dict]:
    """Tumbling windows aligned to the epoch. A trace belongs to the window in which its final
    request event was stamped; all of its events travel with it."""
    by_trace: dict = {}
    completed_at: dict = {}
    for event in events:
        by_trace.setdefault(event["trace_id"], []).append(event)
        if event["step"] == "request" and event["status"] != "received":
            completed_at[event["trace_id"]] = parse_ts(event["ts"])
    if not completed_at:
        return []
    width = timedelta(minutes=minutes)
    epoch = datetime(1970, 1, 1, tzinfo=timezone.utc)
    first = min(completed_at.values())
    last = max(completed_at.values())
    start = epoch + timedelta(seconds=((first - epoch) // width) * width.total_seconds())
    out = []
    while start <= last:
        end = start + width
        traces = [t for t, at in completed_at.items() if start <= at < end]
        out.append({"start": start, "end": end, "events": [e for t in traces for e in by_trace[t]], "requests": len(traces)})
        start = end
    return out


def indicators(events: list[dict], input_rate: float | None = None, output_rate: float | None = None) -> dict:
    """Every indicator an objective or alert may use, from one window's events."""
    s = summarize(events, input_rate, output_rate)
    n = s["requests"]
    if n == 0:
        return {name: None for name in INDICATORS} | {"requests": 0}
    calls = s["usage"]["calls"]
    failures = s["model_call_failures"]
    return {
        "requests": n,
        "availability": (n - s["model_unavailable"]) / n,
        "model_unavailable_rate": s["model_unavailable"] / n,
        "latency_p95_ms": s["latency_ms"]["p95"],
        "latency_p50_ms": s["latency_ms"]["p50"],
        "escalation_rate": s["routes"].get("human_review", 0) / n,
        "drafted_rate": s["drafted"] / n,
        "flagged_draft_rate": s["flagged_drafts"] / n,
        "model_call_failure_rate": failures / (calls + failures) if (calls + failures) else 0.0,
        "retry_rate": s["requests_with_retries"] / n,
        "cost_per_request_usd": s["cost"]["per_request_usd"] if s["cost"] else None,
    }


INDICATORS = ("requests", "availability", "model_unavailable_rate", "latency_p95_ms", "latency_p50_ms", "escalation_rate",
              "drafted_rate", "flagged_draft_rate", "model_call_failure_rate", "retry_rate", "cost_per_request_usd")


def evaluate(events: list[dict], objectives: list[Objective], input_rate: float | None = None, output_rate: float | None = None) -> list[dict]:
    """Per objective, every window with its value and whether the target was met."""
    report = []
    cache: dict = {}
    for objective in objectives:
        if objective.window_minutes not in cache:
            cache[objective.window_minutes] = [(w, indicators(w["events"], input_rate, output_rate)) for w in windows(events, objective.window_minutes)]
        rows = []
        for window, values in cache[objective.window_minutes]:
            value = values.get(objective.indicator)
            enough = window["requests"] >= objective.min_requests and value is not None
            rows.append({
                "start": window["start"].isoformat(timespec="minutes"),
                "end": window["end"].isoformat(timespec="minutes"),
                "requests": window["requests"],
                "value": None if value is None else round(value, 4),
                "met": COMPARISONS[objective.comparison](value, objective.target) if enough else None,
            })
        judged = [r for r in rows if r["met"] is not None]
        verdict = "insufficient data" if not judged else ("met" if all(r["met"] for r in judged) else "missed")
        report.append({"objective": objective.name, "indicator": objective.indicator, "target": objective.target,
                       "comparison": objective.comparison, "window_minutes": objective.window_minutes, "why": objective.why,
                       "windows": rows, "met_windows": sum(1 for r in judged if r["met"]), "judged_windows": len(judged),
                       "verdict": verdict})
    return report


def render(report: list[dict]) -> str:
    lines = ["| Objective | Target | Windows met | Verdict | Values per window |", "| --- | --- | --- | --- | --- |"]
    for row in report:
        values = ", ".join("-" if r["value"] is None else (f"{r['value']:.3f}" if abs(r["value"]) < 100 else f"{r['value']:.0f}") + ("" if r["met"] is None else ("" if r["met"] else "!"))
                           for r in row["windows"])
        lines.append(f"| {row['objective']} | {row['indicator']} {row['comparison']} {row['target']} | {row['met_windows']}/{row['judged_windows']} | {row['verdict']} | {values} |")
    return "\n".join(lines)


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("events")
    parser.add_argument("--objectives", default=str(DEFAULT_OBJECTIVES))
    parser.add_argument("--input-rate", type=float, default=None)
    parser.add_argument("--output-rate", type=float, default=None)
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args(argv)
    report = evaluate(read_events(args.events), load_objectives(Path(args.objectives)), args.input_rate, args.output_rate)
    print(json.dumps(report, indent=2) if args.json else render(report))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
