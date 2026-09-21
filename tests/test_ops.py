"""Objectives and alert rules are evaluated over synthetic event logs with chosen timestamps, so
every trigger and every non-trigger is asserted exactly. Nothing here waits or calls the API."""
import json
import subprocess
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

from ops.alerts import AlertRule, evaluate_alerts, load_rules
from ops.slo import Objective, evaluate, indicators, load_objectives, windows

T0 = datetime(2026, 9, 7, 8, 0, tzinfo=timezone.utc)
VERSIONS = {"app": "2.1.0", "mode": "model", "model": "m", "prompt": "p", "prompt_variant": "v1", "client": "replay"}


def trace(index: int, at: datetime, *, route="draft", unavailable=False, duration_ms=4000.0, flagged=False, tokens=(600, 170)):
    """The events of one completed request, stamped at `at`."""
    tid = f"t{index:04d}"
    ts = at.isoformat(timespec="milliseconds")
    if unavailable:
        route = "human_review"
    reasons = ["classification_unavailable", "unknown_category", "no_reference_article"] if unavailable else ([] if route == "draft" else ["unknown_category"])
    if flagged:
        reasons = ["unverifiable_promise"]
        route = "human_review"
    events = [{"ts": ts, "trace_id": tid, "request_id": f"R{index}", "step": "request", "status": "received", "duration_ms": None, "attrs": {}, "schema": 1}]
    if unavailable:
        events.append({"ts": ts, "trace_id": tid, "request_id": f"R{index}", "step": "classify", "status": "unavailable", "duration_ms": 3500.0,
                       "attrs": {"attempts": 3, "last_error": "LLMTimeout"}, "schema": 1})
        calls, tok = 0, (0, 0)
    else:
        events.append({"ts": ts, "trace_id": tid, "request_id": f"R{index}", "step": "classify", "status": "ok", "duration_ms": duration_ms / 2,
                       "attrs": {"calls": 1, "input_tokens": tokens[0] // 2, "output_tokens": tokens[1] // 2}, "schema": 1})
        events.append({"ts": ts, "trace_id": tid, "request_id": f"R{index}", "step": "draft", "status": "ok", "duration_ms": duration_ms / 2,
                       "attrs": {"calls": 1, "input_tokens": tokens[0] // 2, "output_tokens": tokens[1] // 2}, "schema": 1})
        calls, tok = 2, tokens
    status = "flagged" if flagged else ("escalated" if route == "human_review" else "ok")
    events.append({"ts": ts, "trace_id": tid, "request_id": f"R{index}", "step": "request", "status": status, "duration_ms": duration_ms,
                   "attrs": {"route": route, "reasons": reasons, "drafted": route == "draft" or flagged, "calls": calls,
                             "input_tokens": tok[0], "output_tokens": tok[1], "versions": VERSIONS}, "schema": 1})
    return events


def log(spec):
    """spec: list of (minutes_after_T0, kwargs). Returns a flat event list."""
    events = []
    for index, (minutes, kwargs) in enumerate(spec):
        events += trace(index, T0 + timedelta(minutes=minutes), **kwargs)
    return events


def test_windows_are_aligned_and_carry_whole_traces():
    events = log([(5, {}), (30, {}), (65, {}), (200, {})])
    ws = windows(events, 60)
    assert [w["requests"] for w in ws] == [2, 1, 0, 1]
    assert ws[0]["start"] == T0 and ws[0]["end"] == T0 + timedelta(hours=1)
    assert all(e["trace_id"] in ("t0000", "t0001") for e in ws[0]["events"])
    assert windows([], 60) == []


def test_indicators_from_one_window():
    events = log([(1, {}), (2, {"route": "human_review"}), (3, {"unavailable": True}), (4, {"flagged": True})])
    values = indicators(events, input_rate=1.0, output_rate=5.0)
    assert values["requests"] == 4
    assert values["availability"] == 0.75 and values["model_unavailable_rate"] == 0.25
    assert values["escalation_rate"] == 0.75           # human_review, unavailable, flagged
    assert values["drafted_rate"] == 0.5               # the plain draft and the flagged one
    assert values["flagged_draft_rate"] == 0.25
    assert values["model_call_failure_rate"] == pytest.approx(1 / 7)
    assert values["cost_per_request_usd"] > 0
    assert indicators(events)["cost_per_request_usd"] is None
    assert indicators([])["requests"] == 0


def test_objectives_judge_only_windows_with_enough_requests():
    objective = Objective("Availability", "availability", 0.99, ">=", 60, 3, "why")
    events = log([(1, {}), (2, {}), (3, {"unavailable": True}), (70, {})])   # window 1: 3 requests, 1 unavailable; window 2: 1 request
    report = evaluate(events, [objective])[0]
    assert [w["met"] for w in report["windows"]] == [False, None]
    assert report["verdict"] == "missed" and report["judged_windows"] == 1
    assert evaluate(log([(1, {}), (2, {})]), [objective])[0]["verdict"] == "insufficient data"


def test_cost_objective_without_rates_is_insufficient_data():
    objective = Objective("Spend", "cost_per_request_usd", 0.01, "<=", 60, 1, "why")
    events = log([(1, {})])
    assert evaluate(events, [objective])[0]["verdict"] == "insufficient data"
    assert evaluate(events, [objective], 1.0, 5.0)[0]["verdict"] == "met"


def rule(**overrides):
    base = dict(name="latency", indicator="latency_p95_ms", threshold=8000, comparison=">", window_minutes=60, for_windows=2,
                min_requests=2, severity="medium", owner="on-call", inspect=("durations",), respond="lower concurrency", why="why")
    base.update(overrides)
    return AlertRule(**base)


def test_one_bad_window_is_noise_two_in_a_row_fire():
    slow = {"duration_ms": 20000.0}
    events = log([(1, slow), (2, slow), (61, {}), (62, {}), (121, slow), (122, slow), (181, slow), (182, slow), (241, slow), (242, slow)])
    report = evaluate_alerts(events, [rule()])
    assert len(report["alerts"]) == 1
    alert = report["alerts"][0]
    assert alert["fired_at"] == (T0 + timedelta(hours=4)).isoformat(timespec="minutes")   # end of the second consecutive bad window
    assert [w["value"] for w in alert["windows"]] == [20000.0, 20000.0]
    assert report["noise"]["latency"] == 1                                              # the lone bad first window
    assert [r["fired"] for r in report["history"]["latency"]] == [False, False, False, True, False]  # a third bad window does not re-page


def test_windows_below_min_requests_never_count():
    events = log([(1, {"duration_ms": 20000.0}), (61, {"duration_ms": 20000.0})])
    report = evaluate_alerts(events, [rule(min_requests=2)])
    assert report["alerts"] == [] and not any(r["condition"] for r in report["history"]["latency"])


def test_unavailable_alert_fires_on_one_window_with_the_affected_traces_as_evidence():
    events = log([(1, {}), (2, {"unavailable": True}), (3, {}), (4, {}), (5, {})])
    unavailable = rule(name="model_unavailable", indicator="model_unavailable_rate", threshold=0.05, for_windows=1, min_requests=5, severity="high")
    report = evaluate_alerts(events, [unavailable])
    assert len(report["alerts"]) == 1
    assert report["alerts"][0]["evidence"] == ["t0001"]
    assert report["alerts"][0]["owner"] == "on-call" and report["alerts"][0]["inspect"] == ["durations"]


def test_shipped_rules_and_objectives_load_and_validate(tmp_path):
    rules = load_rules()
    assert {r.name for r in rules} >= {"model_unavailable", "latency_p95", "escalation_share", "flagged_drafts", "spend"}
    assert all(r.owner and r.inspect and r.respond for r in rules)
    objectives = load_objectives()
    assert {o.indicator for o in objectives} >= {"availability", "latency_p95_ms", "escalation_rate", "flagged_draft_rate", "cost_per_request_usd"}
    bad = tmp_path / "rules.json"
    bad.write_text(json.dumps([{"name": "x", "indicator": "latency_p95_ms", "threshold": 1, "comparison": ">=", "window_minutes": 60,
                                "for_windows": 1, "min_requests": 1, "severity": "low", "owner": "o", "inspect": [], "respond": "r", "why": "w"}]))
    with pytest.raises(ValueError, match="comparison"):
        load_rules(bad)
    bad.write_text(json.dumps([{"name": "x", "indicator": "nope", "target": 1, "comparison": ">=", "window_minutes": 60, "min_requests": 1, "why": "w"}]))
    with pytest.raises(ValueError, match="unknown indicator"):
        load_objectives(bad)


def test_the_clean_week_fires_nothing_and_the_incident_week_fires_two():
    from support_assistant.telemetry.events import read_events
    root = Path(__file__).resolve().parent.parent
    rules = load_rules()
    clean = evaluate_alerts(read_events(root / "results" / "events" / "week-1.jsonl"), rules, 1.0, 5.0)
    assert clean["alerts"] == []
    incidents = evaluate_alerts(read_events(root / "results" / "events" / "week-1-incidents.jsonl"), rules, 1.0, 5.0)
    assert [a["rule"] for a in incidents["alerts"]] == ["model_unavailable", "latency_p95"]


def test_replay_traffic_stamps_simulated_time_and_injects_an_outage(tmp_path):
    root = Path(__file__).resolve().parent.parent
    out = tmp_path / "events.jsonl"
    result = subprocess.run([sys.executable, "scripts/replay_traffic.py", "data/traffic/week-1.jsonl", "--events", str(out), "--limit", "6", "--outage", "2:3"],
                            cwd=root, capture_output=True, text=True)
    assert result.returncode == 0, result.stderr
    from support_assistant.telemetry.events import read_events
    rows = read_events(out)
    finals = [r for r in rows if r["step"] == "request" and r["status"] != "received"]
    assert len(finals) == 6
    assert finals[0]["ts"].startswith("2026-09-07T08:")                       # stamped from created_at, not from today
    assert finals[0]["duration_ms"] > 1000                                     # simulated model latency, not replay speed
    assert "classification_unavailable" in finals[1]["attrs"]["reasons"]       # the injected outage hit request 2
    assert finals[1]["duration_ms"] > finals[0]["duration_ms"]                 # backoff counted in simulated time
