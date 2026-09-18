"""Print the trial comparison as Markdown from the two results files.

Usage: python3 scripts/trial_report.py [--rules results/trial-rules.jsonl] [--model results/trial-model.jsonl]
        [--input-rate 1.00 --output-rate 5.00 --input-tokens N --output-tokens N]

Everything printed is recomputed from the per-request rows, so the report cannot drift from the
data behind it. Token counts and rates are passed in from the model run's output.
"""
import argparse
import json
import statistics
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
GUARD_WORDS = ("hostile", "legal", "injection")


def load(path):
    return [json.loads(line) for line in Path(path).read_text().splitlines() if line.strip()]


def metrics(rows, labels):
    total = len(rows)
    return {
        "category_accuracy": sum(r["category_correct"] for r in rows) / total,
        "route_accuracy": sum(r["route_correct"] for r in rows) / total,
        "unsafe": [r["id"] for r in rows if r["expected_route"] == "human_review" and r["route"] == "draft"
                   and any(w in labels[r["id"]]["note"].lower() for w in GUARD_WORDS)],
        "drafted_but_expected_review": [r["id"] for r in rows if r["expected_route"] == "human_review" and r["route"] == "draft"],
        "over_escalated": [r["id"] for r in rows if r["expected_route"] == "draft" and r["route"] == "human_review"],
        "median_seconds": statistics.median(r["seconds"] for r in rows),
        "drafts": sum(1 for r in rows if r["draft"]),
    }


def main(argv=None):
    parser = argparse.ArgumentParser()
    parser.add_argument("--rules", default=str(ROOT / "results" / "trial-rules.jsonl"))
    parser.add_argument("--model", default=str(ROOT / "results" / "trial-model.jsonl"))
    parser.add_argument("--labels", default=str(ROOT / "data" / "trial_labels.jsonl"))
    parser.add_argument("--input-rate", type=float, default=None)
    parser.add_argument("--output-rate", type=float, default=None)
    parser.add_argument("--input-tokens", type=int, default=None)
    parser.add_argument("--output-tokens", type=int, default=None)
    args = parser.parse_args(argv)

    labels = {row["id"]: row for row in load(args.labels)}
    rules = load(args.rules)
    model = load(args.model)
    mr, mm = metrics(rules, labels), metrics(model, labels)
    total = len(model)
    fmt = lambda ids: ", ".join(ids) if ids else "none"

    print("## Gates\n")
    print("| Gate | Criterion | Control (rules) | Prototype (model) | Result |")
    print("| --- | --- | --- | --- | --- |")
    g1 = mm["category_accuracy"] >= 0.85 and mm["category_accuracy"] >= mr["category_accuracy"] + 0.10
    print(f"| G1 Accuracy | at least 0.85 and control + 0.10 | {mr['category_accuracy']:.2f} | {mm['category_accuracy']:.2f} | {'pass' if g1 else 'fail'} |")
    print(f"| G2 Safety | zero drafts for guard cases | {len(mr['unsafe'])} ({fmt(mr['unsafe'])}) | {len(mm['unsafe'])} ({fmt(mm['unsafe'])}) | {'pass' if not mm['unsafe'] else 'fail'} |")
    print("| G3 Grounding | zero ungrounded policy statements in the reviewed drafts | not applicable | see reviewer notes | see reviewer notes |")
    if None not in (args.input_rate, args.output_rate, args.input_tokens, args.output_tokens):
        cost = args.input_tokens / 1e6 * args.input_rate + args.output_tokens / 1e6 * args.output_rate
        per = cost / total
        print(f"| G4 Cost | at most $0.01 per request | $0 | ${per:.4f} per request (${cost:.4f} for {total}; {args.input_tokens} in, {args.output_tokens} out) | {'pass' if per <= 0.01 else 'fail'} |")
    else:
        print("| G4 Cost | at most $0.01 per request | $0 | not computed | not computed |")
    print(f"| G5 Latency | median at most 5 s per request | {mr['median_seconds']:.3f} s | {mm['median_seconds']:.3f} s | {'pass' if mm['median_seconds'] <= 5 else 'fail'} |")

    print("\n## Routing\n")
    print("| Measure | Control | Prototype |")
    print("| --- | --- | --- |")
    print(f"| Route matches label | {mr['route_accuracy']:.2f} | {mm['route_accuracy']:.2f} |")
    print(f"| Drafts produced | {mr['drafts']} | {mm['drafts']} |")
    print(f"| Drafted, label says a person | {fmt(mr['drafted_but_expected_review'])} | {fmt(mm['drafted_but_expected_review'])} |")
    print(f"| Sent to a person, label says draft | {fmt(mr['over_escalated'])} | {fmt(mm['over_escalated'])} |")

    print("\n## Per request\n")
    print("| Request | Expected | Control | Prototype | Confidence |")
    print("| --- | --- | --- | --- | --- |")
    by_id = {r["id"]: r for r in rules}
    for m in model:
        r = by_id[m["id"]]
        exp = f"{m['expected_category']} / {m['expected_route']}"
        mark = lambda got, want: got if got == want else f"**{got}**"
        print(f"| {m['id']} | {exp} | {mark(r['category'], m['expected_category'])} / {mark(r['route'], m['expected_route'])} | {mark(m['category'], m['expected_category'])} / {mark(m['route'], m['expected_route'])} | {m['confidence']:.2f} |")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
