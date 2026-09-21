"""Recurring evaluation: run the suites on a schedule, compare with the reference runs, and keep
every new failure.

    python3 -m ops.scheduled_eval --as-of 2026-09-13 --traffic data/traffic/week-1.jsonl --label week-1
    python3 -m ops.scheduled_eval --as-of 2026-09-20 --traffic data/traffic/week-2.jsonl --label week-2 --variant v1

Each run, on the replay client so it is free and deterministic:

1. the development split of dataset v1 and the adversarial probes, compared criterion by
   criterion with the reference runs recorded when the current version shipped; a case that was
   acceptable in the reference and is not now is a **regression** and is written to
   results/evals/scheduled/new-failures.jsonl with the run that found it;
2. the cases behind a recorded traffic window, weighted by how often each appeared in the
   window, so the numbers say what customers experienced that week rather than what the
   dataset contains; the previous window's numbers sit beside them.

The schedule itself is whatever runs this command (a weekly job, or by hand after a change).
`--as-of` names the run; the results carry it so reports can be compared across weeks.
"""
import argparse
import dataclasses
import json
from collections import Counter
from datetime import datetime
from pathlib import Path

from evals.runner import RESULTS_DIR, load_run, run, traffic_case_ids
from support_assistant.config import load_settings
from support_assistant.llm.factory import build_client

SCHEDULED_DIR = RESULTS_DIR / "scheduled"
NEW_FAILURES = SCHEDULED_DIR / "new-failures.jsonl"
REFERENCES = {"v1": {"v1": "v1-development-after-repair", "adv-v1": "adv-v1-development-after-repair"},
              "v2": {"v1": "v1-development-candidate", "adv-v1": "adv-v1-development-candidate"}}


def compare_with_reference(items: list[dict], reference_items: list[dict]) -> dict:
    """Per-case comparison with the reference run of the same suite."""
    ref = {i["id"]: i for i in reference_items}
    regressions, recoveries, changed = [], [], []
    for item in items:
        before = ref.get(item["id"])
        if before is None:
            continue
        if before["acceptable"] and not item["acceptable"]:
            regressions.append({"id": item["id"], "before": before["verdicts"], "now": item["verdicts"], "reasons": item["reasons"]})
        elif item["acceptable"] and not before["acceptable"]:
            recoveries.append(item["id"])
        elif before["verdicts"] != item["verdicts"]:
            changed.append(item["id"])
    return {"regressions": regressions, "recoveries": recoveries, "changed_verdicts": changed, "compared": sum(1 for i in items if i["id"] in ref)}


def weighted_window(items: list[dict], traffic_path: Path) -> dict:
    """Rubric outcomes weighted by how many requests in the window each case stood for."""
    weights = Counter()
    for line in Path(traffic_path).read_text(encoding="utf-8").splitlines():
        if line.strip():
            weights[json.loads(line).get("source_case")] += 1
    by_id = {i["id"]: i for i in items}
    total = sum(w for case_id, w in weights.items() if case_id in by_id)
    if not total:
        return {"requests": 0}

    def rate(test):
        return round(sum(w for case_id, w in weights.items() if case_id in by_id and test(by_id[case_id])) / total, 3)

    failing = Counter({case_id: w for case_id, w in weights.items() if case_id in by_id and not by_id[case_id]["acceptable"]})
    return {
        "requests": total,
        "acceptable_rate": rate(lambda i: bool(i["acceptable"])),
        "missed_escalation_rate": rate(lambda i: i["verdicts"]["R2"] == "missed"),
        "over_escalation_rate": rate(lambda i: i["verdicts"]["R2"] == "over"),
        "unsupported_statement_rate": rate(lambda i: i["verdicts"].get("R3") == "fail"),
        "incomplete_rate": rate(lambda i: i["verdicts"].get("R4") in ("fail", "partial")),
        "wrong_article_rate": rate(lambda i: i["expected_route"] == "draft" and i["article"] != i["expected_article"]),
        "top_failing_cases": [{"id": case_id, "requests": w, "verdicts": {k: v for k, v in by_id[case_id]["verdicts"].items() if v != "pass"}} for case_id, w in failing.most_common(5)],
    }


def record_new_failures(as_of: str, run_id: str, regressions: list[dict]) -> int:
    SCHEDULED_DIR.mkdir(parents=True, exist_ok=True)
    known = set()
    if NEW_FAILURES.exists():
        for line in NEW_FAILURES.read_text(encoding="utf-8").splitlines():
            if line.strip():
                row = json.loads(line)
                known.add((row["run"], row["id"]))
    added = 0
    with NEW_FAILURES.open("a", encoding="utf-8") as handle:
        for regression in regressions:
            if (run_id, regression["id"]) in known:
                continue
            handle.write(json.dumps({"as_of": as_of, "run": run_id, **regression}) + "\n")
            added += 1
    return added


def previous_window(label: str, as_of: str, variant: str) -> dict | None:
    """The most recent earlier run on the same variant that scored a traffic window."""
    candidates = []
    for path in SCHEDULED_DIR.glob("*/summary.json"):
        if path.parent.name == label:
            continue
        data = json.loads(path.read_text(encoding="utf-8"))
        if data.get("traffic") and data.get("variant") == variant and data["as_of"] < as_of:
            candidates.append((data["as_of"], path.parent.name, data))
    if not candidates:
        return None
    _, name, data = max(candidates)
    return {"label": name, "as_of": data["as_of"], **data["traffic"]["weighted"]}


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--as-of", required=True, help="date the run stands for, YYYY-MM-DD")
    parser.add_argument("--label", required=True, help="folder name under results/evals/scheduled/")
    parser.add_argument("--traffic", default=None, help="recorded traffic window to score, weighted by request counts")
    parser.add_argument("--variant", choices=("v1", "v2"), default="v1")
    args = parser.parse_args(argv)
    datetime.strptime(args.as_of, "%Y-%m-%d")

    settings = dataclasses.replace(load_settings(), mode="model", llm_client="replay", prompt_variant=args.variant)
    client, judge = build_client(settings), build_client(settings)
    out_dir = SCHEDULED_DIR / args.label
    out_dir.mkdir(parents=True, exist_ok=True)
    report = {"as_of": args.as_of, "label": args.label, "variant": args.variant, "suites": {}, "traffic": None, "new_failures_recorded": 0}

    for dataset in ("v1", "adv-v1"):
        run_id = f"{args.label}-{dataset}"
        summary = run(dataset, "development", settings, client, judge, run_id, results_dir=out_dir, log=lambda *_: None)
        items, _ = load_run(out_dir / run_id)
        reference_id = REFERENCES[args.variant][dataset]
        comparison = None
        if reference_id and (RESULTS_DIR / reference_id).exists():
            reference_items, _ = load_run(RESULTS_DIR / reference_id)
            comparison = compare_with_reference(items, reference_items)
            report["new_failures_recorded"] += record_new_failures(args.as_of, run_id, comparison["regressions"])
        report["suites"][dataset] = {"run": run_id, "cases": summary["cases"], "acceptable": summary["acceptable"], "criteria": summary["criteria"],
                                     "reference": reference_id, "comparison": comparison}
        line = f"{dataset}: {summary['acceptable']}/{summary['cases']} acceptable"
        if comparison:
            line += f"; vs {reference_id}: {len(comparison['regressions'])} regressions, {len(comparison['recoveries'])} recoveries, {len(comparison['changed_verdicts'])} other verdict changes"
        print(line)

    if args.traffic:
        case_ids = traffic_case_ids(Path(args.traffic))
        run_id = f"{args.label}-traffic"
        summary = run("v1", None, settings, client, judge, run_id, results_dir=out_dir, log=lambda *_: None, case_ids=case_ids)
        items, _ = load_run(out_dir / run_id)
        weighted = weighted_window(items, Path(args.traffic))
        report["traffic"] = {"file": str(args.traffic), "run": run_id, "cases": summary["cases"], "weighted": weighted, "previous": previous_window(args.label, args.as_of, args.variant)}
        print(f"traffic {args.traffic}: {weighted['requests']} requests over {summary['cases']} cases; acceptable {weighted['acceptable_rate']:.0%}, "
              f"missed escalation {weighted['missed_escalation_rate']:.0%}, over-escalation {weighted['over_escalation_rate']:.0%}, "
              f"unsupported statements {weighted['unsupported_statement_rate']:.0%}, wrong article {weighted['wrong_article_rate']:.0%}")
        if report["traffic"]["previous"]:
            prev = report["traffic"]["previous"]
            print(f"previous window {prev['label']} ({prev['as_of']}): acceptable {prev['acceptable_rate']:.0%}, missed escalation {prev['missed_escalation_rate']:.0%}, "
                  f"unsupported statements {prev['unsupported_statement_rate']:.0%}, wrong article {prev['wrong_article_rate']:.0%}")
        print("most frequent failing cases: " + ", ".join(f"{c['id']} x{c['requests']} {c['verdicts']}" for c in weighted["top_failing_cases"]))

    (out_dir / "summary.json").write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    print(f"new failures recorded: {report['new_failures_recorded']}; wrote {out_dir / 'summary.json'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
