"""Drift signals and the recurring evaluation's bookkeeping, on synthetic events and items."""
import json

from ops import scheduled_eval
from ops.drift import compare, profile
from ops.scheduled_eval import compare_with_reference, record_new_failures, weighted_window
from tests.test_ops import log

VERSIONS_V2 = {"app": "2.1.0", "mode": "model", "model": "m", "prompt": "q", "prompt_variant": "v2", "client": "replay"}


def week(categories, n_per_category, escalate=False, versions=None, duration_ms=4000.0):
    """A synthetic window: n requests per category, optionally escalated, at one version."""
    spec = []
    minute = 0
    for category in categories:
        for _ in range(n_per_category):
            spec.append((minute, {"route": "human_review" if escalate else "draft", "duration_ms": duration_ms}))
            minute += 1
    events = log(spec)
    finals = [e for e in events if e["step"] == "request" and e["status"] != "received"]
    for index, event in enumerate(finals):
        event["attrs"]["category"] = categories[index // n_per_category]
        if versions:
            event["attrs"]["versions"] = versions
    return events


def test_profile_reads_mix_rates_and_versions():
    events = week(["billing", "other"], 30)
    p = profile(events)
    assert p["requests"] == 60 and p["categories"] == {"billing": 0.5, "other": 0.5}
    assert p["escalation_rate"] == 0.0 and p["drafted_rate"] == 1.0
    assert p["versions"][0]["prompt_variant"] == "v1"
    assert profile([])["requests"] == 0


def test_a_mix_shift_with_unchanged_versions_is_an_input_signal():
    baseline = profile(week(["billing", "orders_shipping"], 30))
    recent = profile(week(["billing", "other"], 30, escalate=True))
    report = compare(baseline, recent)
    kinds = {s["kind"] for s in report["signals"]}
    assert kinds == {"input_shift"}
    statements = " ".join(s["statement"] for s in report["signals"])
    assert "other requests moved from 0% to 50%" in statements and "escalation rate moved from 0% to 100%" in statements
    assert all(s["does_not_prove"] for s in report["signals"])
    assert not report["versions_changed"]


def test_a_version_change_makes_every_signal_a_system_change():
    baseline = profile(week(["billing"], 60))
    recent = profile(week(["billing"], 60, escalate=True, versions=VERSIONS_V2))
    report = compare(baseline, recent)
    assert report["versions_changed"]
    assert {s["kind"] for s in report["signals"]} == {"system_change"}


def test_small_windows_produce_no_share_signals():
    report = compare(profile(week(["billing"], 10)), profile(week(["other"], 10, escalate=True)))
    assert not report["enough_data"] and report["signals"] == []


def test_a_latency_jump_is_a_performance_signal():
    report = compare(profile(week(["billing"], 60)), profile(week(["billing"], 60, duration_ms=9000.0)))
    assert [s["kind"] for s in report["signals"]] == ["performance"]


def item(id_, acceptable, verdicts=None, article="a", expected="a", route="draft"):
    return {"id": id_, "acceptable": acceptable, "verdicts": verdicts or {"R1": "pass", "R2": "pass", "R3": "pass", "R4": "pass", "R5": "pass"},
            "reasons": [], "article": article, "expected_article": expected, "expected_route": route}


def test_reference_comparison_finds_regressions_and_recoveries():
    fail = {"R1": "fail", "R2": "missed", "R3": "pass", "R4": "pass", "R5": "pass"}
    reference = [item("a", True), item("b", False, fail), item("c", True), item("d", True)]
    now = [item("a", False, fail), item("b", True), item("c", True, {"R1": "pass", "R2": "pass", "R3": "pass", "R4": "partial", "R5": "pass"}), item("e", True)]
    report = compare_with_reference(now, reference)
    assert [r["id"] for r in report["regressions"]] == ["a"]
    assert report["recoveries"] == ["b"] and report["changed_verdicts"] == ["c"] and report["compared"] == 3


def test_new_failures_are_recorded_once_per_run(tmp_path, monkeypatch):
    monkeypatch.setattr(scheduled_eval, "SCHEDULED_DIR", tmp_path)
    monkeypatch.setattr(scheduled_eval, "NEW_FAILURES", tmp_path / "new-failures.jsonl")
    regressions = [{"id": "a", "before": {}, "now": {"R2": "missed"}, "reasons": []}]
    assert record_new_failures("2026-09-20", "run-1", regressions) == 1
    assert record_new_failures("2026-09-20", "run-1", regressions) == 0
    assert record_new_failures("2026-09-27", "run-2", regressions) == 1
    rows = [json.loads(l) for l in (tmp_path / "new-failures.jsonl").read_text().splitlines()]
    assert [(r["run"], r["id"]) for r in rows] == [("run-1", "a"), ("run-2", "a")]


def test_traffic_weighting_counts_requests_not_cases(tmp_path):
    traffic = tmp_path / "traffic.jsonl"
    traffic.write_text("\n".join(json.dumps({"id": f"W-{i}", "source_case": case}) for i, case in enumerate(["a", "a", "a", "b", "c"])) + "\n")
    items = [item("a", True), item("b", False, {"R1": "fail", "R2": "missed", "R3": "pass", "R4": "pass", "R5": "pass"}, route="human_review"),
             item("c", False, {"R1": "pass", "R2": "pass", "R3": "fail", "R4": "pass", "R5": "pass"}, article="x", expected="y")]
    weighted = weighted_window(items, traffic)
    assert weighted["requests"] == 5
    assert weighted["acceptable_rate"] == 0.6 and weighted["missed_escalation_rate"] == 0.2
    assert weighted["unsupported_statement_rate"] == 0.2 and weighted["wrong_article_rate"] == 0.2
    assert weighted["top_failing_cases"][0]["id"] in ("b", "c")
    assert weighted_window(items, tmp_path / "missing.jsonl" if False else traffic)["requests"] == 5


def test_the_two_recorded_weeks_differ_in_mix_and_the_suites_did_not_change():
    from pathlib import Path
    root = Path(__file__).resolve().parent.parent
    week1 = json.loads((root / "results/evals/scheduled/2026-09-13-week-1/summary.json").read_text())
    week2 = json.loads((root / "results/evals/scheduled/2026-09-20-week-2/summary.json").read_text())
    for report in (week1, week2):
        for suite in report["suites"].values():
            assert suite["comparison"]["regressions"] == []
    assert week2["traffic"]["weighted"]["missed_escalation_rate"] > week1["traffic"]["weighted"]["missed_escalation_rate"] + 0.1
    drift = json.loads((root / "results/drift/week-2-vs-week-1.json").read_text())
    assert {s["kind"] for s in drift["comparison"]["signals"]} == {"input_shift"}
