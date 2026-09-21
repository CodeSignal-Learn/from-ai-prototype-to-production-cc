"""Alert rules over event windows: what fires, when, for whom, and what to look at.

    python3 -m ops.alerts results/events/week-1-outage.jsonl
    python3 -m ops.alerts results/events/week-1.jsonl --rules ops/alert_rules.json --input-rate 1.00 --output-rate 5.00

A rule names an indicator, a threshold, a window, and how many consecutive windows the condition
must hold before anyone is told (`for_windows`). One bad window is noise for most indicators;
persistence is what separates a change from a blip. A rule also names the owner, what evidence
to inspect, and what to do, so an alert is an instruction and not a number. Rules are data in
ops/alert_rules.json. Evaluation is deterministic over a log, which is how the rules are tested:
replay a week with an injected outage and check what fires, and replay the clean week and check
what does not.
"""
import argparse
import json
from dataclasses import dataclass
from pathlib import Path

from support_assistant.telemetry.events import read_events

from .slo import OPS_DIR, indicators, windows

DEFAULT_RULES = OPS_DIR / "alert_rules.json"
COMPARISONS = {">": lambda value, threshold: value > threshold, "<": lambda value, threshold: value < threshold}


@dataclass(frozen=True)
class AlertRule:
    name: str
    indicator: str
    threshold: float
    comparison: str          # ">" or "<"
    window_minutes: int
    for_windows: int
    min_requests: int
    severity: str
    owner: str
    inspect: tuple
    respond: str
    why: str


def load_rules(path: Path = DEFAULT_RULES) -> list[AlertRule]:
    rules = []
    for row in json.loads(Path(path).read_text(encoding="utf-8")):
        if row["comparison"] not in COMPARISONS:
            raise ValueError(f"rule {row['name']}: comparison must be > or <")
        if row["for_windows"] < 1:
            raise ValueError(f"rule {row['name']}: for_windows must be at least 1")
        rules.append(AlertRule(**dict(row, inspect=tuple(row["inspect"]))))
    return rules


def evidence_for(rule: AlertRule, window: dict) -> list[str]:
    """Trace ids a responder should open first for this rule in this window."""
    finals = [e for e in window["events"] if e["step"] == "request" and e["status"] != "received"]
    if rule.indicator in ("model_unavailable_rate", "availability"):
        picked = [e for e in finals if any(r in ("classification_unavailable", "draft_unavailable") for r in e["attrs"].get("reasons", []))]
    elif rule.indicator in ("latency_p95_ms", "latency_p50_ms"):
        picked = sorted(finals, key=lambda e: e.get("duration_ms") or 0, reverse=True)[:3]
    elif rule.indicator == "flagged_draft_rate":
        picked = [e for e in finals if e["status"] == "flagged"]
    elif rule.indicator == "escalation_rate":
        picked = [e for e in finals if e["attrs"].get("route") == "human_review"][:3]
    else:
        picked = []
    return [e["trace_id"] for e in picked[:5]]


def evaluate_alerts(events: list[dict], rules: list[AlertRule], input_rate: float | None = None, output_rate: float | None = None) -> dict:
    """Walk the windows of each rule and fire when its condition has held for `for_windows` in a row."""
    alerts = []
    history = {}
    cache: dict = {}
    for rule in rules:
        if rule.window_minutes not in cache:
            cache[rule.window_minutes] = [(w, indicators(w["events"], input_rate, output_rate)) for w in windows(events, rule.window_minutes)]
        streak = 0
        rows = []
        for window, values in cache[rule.window_minutes]:
            value = values.get(rule.indicator)
            enough = window["requests"] >= rule.min_requests and value is not None
            condition = bool(enough and COMPARISONS[rule.comparison](value, rule.threshold))
            streak = streak + 1 if condition else 0
            fired = condition and streak == rule.for_windows
            if condition and streak > rule.for_windows:
                fired = False  # already firing; a real system would keep the alert open, not re-page
            rows.append({"start": window["start"].isoformat(timespec="minutes"), "end": window["end"].isoformat(timespec="minutes"),
                         "requests": window["requests"], "value": None if value is None else round(value, 4),
                         "condition": condition, "enough_data": enough, "streak": streak, "fired": fired})
            if fired:
                streak_rows = rows[-rule.for_windows:]
                alerts.append({
                    "rule": rule.name, "severity": rule.severity, "owner": rule.owner,
                    "fired_at": window["end"].isoformat(timespec="minutes"),
                    "windows": [{"start": r["start"], "end": r["end"], "value": r["value"], "requests": r["requests"]} for r in streak_rows],
                    "threshold": f"{rule.indicator} {rule.comparison} {rule.threshold} for {rule.for_windows} window(s) of {rule.window_minutes} min",
                    "evidence": evidence_for(rule, window),
                    "inspect": list(rule.inspect), "respond": rule.respond,
                })
        history[rule.name] = rows
    return {"alerts": alerts, "history": history, "noise": {rule.name: noise_windows(history[rule.name], rule.for_windows) for rule in rules}}


def noise_windows(rows: list[dict], for_windows: int) -> int:
    """Windows where the condition held but the run it belonged to was too short to fire."""
    noise = 0
    run = 0
    for row in rows + [{"condition": False}]:
        if row["condition"]:
            run += 1
        else:
            if 0 < run < for_windows:
                noise += run
            run = 0
    return noise


def render(report: dict) -> str:
    lines = []
    if not report["alerts"]:
        lines.append("no alerts fired")
    for alert in report["alerts"]:
        lines.append(f"ALERT {alert['severity'].upper()} {alert['rule']} at {alert['fired_at']}  owner: {alert['owner']}")
        lines.append(f"  condition: {alert['threshold']}")
        lines.append("  windows: " + "; ".join(f"{w['start'][11:16]}-{w['end'][11:16]} value {w['value']} n={w['requests']}" for w in alert["windows"]))
        if alert["evidence"]:
            lines.append("  open first: " + ", ".join(alert["evidence"]))
        for item in alert["inspect"]:
            lines.append(f"  inspect: {item}")
        lines.append(f"  respond: {alert['respond']}")
    lines.append("")
    lines.append("| Rule | Windows | Condition true | Fired | Single-window noise |")
    lines.append("| --- | --- | --- | --- | --- |")
    for name, rows in report["history"].items():
        lines.append(f"| {name} | {len(rows)} | {sum(1 for r in rows if r['condition'])} | {sum(1 for r in rows if r['fired'])} | {report['noise'][name]} |")
    return "\n".join(lines)


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("events")
    parser.add_argument("--rules", default=str(DEFAULT_RULES))
    parser.add_argument("--input-rate", type=float, default=None)
    parser.add_argument("--output-rate", type=float, default=None)
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args(argv)
    report = evaluate_alerts(read_events(args.events), load_rules(Path(args.rules)), args.input_rate, args.output_rate)
    print(json.dumps(report, indent=2) if args.json else render(report))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
