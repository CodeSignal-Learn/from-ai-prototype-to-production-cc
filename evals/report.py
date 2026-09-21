"""Compare a baseline and a candidate on the same cases, over repeated runs.

    python3 -m evals.report --baseline v1-held_out-baseline-r1 v1-held_out-baseline-r2 v1-held_out-baseline-r3 \
                            --candidate v1-held_out-candidate-r1 v1-held_out-candidate-r2 v1-held_out-candidate-r3 \
                            --out results/evals/comparison/held-out.json

The protocol is fixed here so that nobody compares unlike things: every run must be on the same
dataset version, checksum, and split; all baseline runs must share one prompt version and all
candidate runs another. Repeats are live runs of the same prompts, so the spread across repeats
is the variability of the model, and a difference between baseline and candidate smaller than
that spread is not a difference. The report prints counts per repeat, mean and range per side,
per-category and per-tag deltas, and the paired list of cases that improved or regressed. It
computes no recommendation; that is written by a person in docs/eval-comparison.md from these
numbers, with the sample limits stated.
"""
import argparse
import json
from collections import Counter, defaultdict
from pathlib import Path

from .runner import RESULTS_DIR, load_run


class ProtocolError(ValueError):
    """The runs are not comparable."""


def load_side(run_ids: list[str], results_dir: Path) -> list[tuple[list[dict], dict]]:
    return [load_run(results_dir / run_id) for run_id in run_ids]


def check_protocol(baseline: list[tuple[list[dict], dict]], candidate: list[tuple[list[dict], dict]]) -> dict:
    runs = baseline + candidate
    keys = {(s["dataset"], s["dataset_sha256"], s["split"]) for _, s in runs}
    if len(keys) != 1:
        raise ProtocolError(f"runs span different datasets or splits: {sorted(keys)}")
    ids = [tuple(sorted(i["id"] for i in items)) for items, _ in runs]
    if len(set(ids)) != 1:
        raise ProtocolError("runs do not cover the same cases")
    base_prompts = {s["versions"]["prompt"] for _, s in baseline}
    cand_prompts = {s["versions"]["prompt"] for _, s in candidate}
    if len(base_prompts) != 1 or len(cand_prompts) != 1:
        raise ProtocolError("each side must use one prompt version across its repeats")
    if base_prompts == cand_prompts:
        raise ProtocolError("baseline and candidate use the same prompt version; nothing to compare")
    judges = {json.dumps(s["judge"], sort_keys=True) for _, s in runs}
    if len(judges) != 1:
        raise ProtocolError("runs were judged by different judges")
    if any(s["unjudged"] for _, s in runs):
        raise ProtocolError("a run has unjudged items; every item must carry a verdict")
    dataset, sha, split = next(iter(keys))
    return {"dataset": dataset, "dataset_sha256": sha, "split": split, "cases": len(ids[0]),
            "baseline_prompt": next(iter(base_prompts)), "candidate_prompt": next(iter(cand_prompts)),
            "baseline_variant": baseline[0][1]["versions"].get("prompt_variant") or "v1",
            "candidate_variant": candidate[0][1]["versions"].get("prompt_variant") or "v1",
            "judge": runs[0][1]["judge"], "repeats": {"baseline": len(baseline), "candidate": len(candidate)}}


MEASURES = (
    ("acceptable", lambda i: bool(i["acceptable"])),
    ("R1_pass", lambda i: i["verdicts"]["R1"] == "pass"),
    ("R2_missed", lambda i: i["verdicts"]["R2"] == "missed"),
    ("R2_over", lambda i: i["verdicts"]["R2"] == "over"),
    ("R3_fail", lambda i: i["verdicts"].get("R3") == "fail"),
    ("R4_fail", lambda i: i["verdicts"].get("R4") == "fail"),
    ("R4_partial", lambda i: i["verdicts"].get("R4") == "partial"),
    ("R5_fail", lambda i: i["verdicts"]["R5"] == "fail"),
    ("drafted", lambda i: bool(i["draft"])),
    ("article_correct", lambda i: i["article"] == i["expected_article"]),
)


def counts(items: list[dict]) -> dict:
    return {name: sum(1 for i in items if test(i)) for name, test in MEASURES}


def spread(per_repeat: list[dict]) -> dict:
    out = {}
    for name, _ in MEASURES:
        values = [c[name] for c in per_repeat]
        out[name] = {"mean": round(sum(values) / len(values), 2), "min": min(values), "max": max(values), "values": values}
    return out


def by_group(side: list[tuple[list[dict], dict]], key) -> dict:
    """Mean acceptable count per group (category or tag) across repeats."""
    totals: dict = defaultdict(lambda: {"cases": 0, "acceptable": 0.0})
    n = len(side)
    for items, _ in side:
        for item in items:
            for group in key(item):
                totals[group]["acceptable"] += bool(item["acceptable"]) / n
    for item in side[0][0]:
        for group in key(item):
            totals[group]["cases"] += 1
    return {g: {"cases": v["cases"], "acceptable_mean": round(v["acceptable"], 2)} for g, v in sorted(totals.items())}


def paired(baseline: list[tuple[list[dict], dict]], candidate: list[tuple[list[dict], dict]]) -> dict:
    """Per case: in how many repeats each side was acceptable, and which cases moved."""
    def tally(side):
        acc: Counter = Counter()
        verdicts: dict = defaultdict(list)
        for items, _ in side:
            for item in items:
                acc[item["id"]] += bool(item["acceptable"])
                verdicts[item["id"]].append({k: v for k, v in item["verdicts"].items() if v != "pass"} or {"all": "pass"})
        return acc, verdicts
    base_acc, base_v = tally(baseline)
    cand_acc, cand_v = tally(candidate)
    nb, nc = len(baseline), len(candidate)
    improved, regressed, unstable = [], [], []
    for case_id in sorted(base_acc.keys() | cand_acc.keys()):
        b, c = base_acc[case_id] / nb, cand_acc[case_id] / nc
        row = {"id": case_id, "baseline_acceptable": f"{base_acc[case_id]}/{nb}", "candidate_acceptable": f"{cand_acc[case_id]}/{nc}",
               "baseline_failures": base_v[case_id], "candidate_failures": cand_v[case_id]}
        if c > b:
            improved.append(row)
        elif c < b:
            regressed.append(row)
        if 0 < base_acc[case_id] < nb or 0 < cand_acc[case_id] < nc:
            unstable.append(case_id)
    return {"improved": improved, "regressed": regressed, "unstable_across_repeats": unstable}


def compare(baseline: list[tuple[list[dict], dict]], candidate: list[tuple[list[dict], dict]]) -> dict:
    protocol = check_protocol(baseline, candidate)
    base_counts = [counts(items) for items, _ in baseline]
    cand_counts = [counts(items) for items, _ in candidate]
    tags = lambda item: item["tags"] or ["untagged"]
    category = lambda item: [item["expected_category"]]
    return {
        "protocol": protocol,
        "baseline": {"runs": [s["run_id"] for _, s in baseline], "per_repeat": base_counts, "spread": spread(base_counts)},
        "candidate": {"runs": [s["run_id"] for _, s in candidate], "per_repeat": cand_counts, "spread": spread(cand_counts)},
        "delta_mean": {name: round(spread(cand_counts)[name]["mean"] - spread(base_counts)[name]["mean"], 2) for name, _ in MEASURES},
        "by_category": {"baseline": by_group(baseline, category), "candidate": by_group(candidate, category)},
        "by_tag": {"baseline": by_group(baseline, tags), "candidate": by_group(candidate, tags)},
        "paired": paired(baseline, candidate),
    }


def render(report: dict) -> str:
    p = report["protocol"]
    lines = [f"Protocol: dataset {p['dataset']} ({p['dataset_sha256'][:12]}), split {p['split']}, {p['cases']} cases; "
             f"baseline {p['baseline_variant']} prompt {p['baseline_prompt']} x{p['repeats']['baseline']} repeats; "
             f"candidate {p['candidate_variant']} prompt {p['candidate_prompt']} x{p['repeats']['candidate']} repeats; judge {p['judge']}",
             "", "| Measure | Baseline mean (min-max) | Candidate mean (min-max) | Delta |", "| --- | --- | --- | --- |"]
    for name, _ in MEASURES:
        b, c = report["baseline"]["spread"][name], report["candidate"]["spread"][name]
        lines.append(f"| {name} | {b['mean']} ({b['min']}-{b['max']}) | {c['mean']} ({c['min']}-{c['max']}) | {report['delta_mean'][name]:+} |")
    lines += ["", "| Category | Cases | Baseline acceptable (mean) | Candidate acceptable (mean) |", "| --- | --- | --- | --- |"]
    for group, row in report["by_category"]["baseline"].items():
        lines.append(f"| {group} | {row['cases']} | {row['acceptable_mean']} | {report['by_category']['candidate'][group]['acceptable_mean']} |")
    lines += ["", "| Tag | Cases | Baseline acceptable (mean) | Candidate acceptable (mean) |", "| --- | --- | --- | --- |"]
    for group, row in report["by_tag"]["baseline"].items():
        lines.append(f"| {group} | {row['cases']} | {row['acceptable_mean']} | {report['by_tag']['candidate'][group]['acceptable_mean']} |")
    pr = report["paired"]
    lines += ["", f"Improved: {len(pr['improved'])}  Regressed: {len(pr['regressed'])}  Unstable across repeats: {len(pr['unstable_across_repeats'])}"]
    for row in pr["regressed"]:
        lines.append(f"  regressed {row['id']}: baseline {row['baseline_acceptable']} -> candidate {row['candidate_acceptable']}; candidate failures {row['candidate_failures']}")
    return "\n".join(lines)


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--baseline", nargs="+", required=True, help="run ids under results/evals/")
    parser.add_argument("--candidate", nargs="+", required=True)
    parser.add_argument("--out", default=None, help="write the report as JSON here")
    args = parser.parse_args(argv)
    report = compare(load_side(args.baseline, RESULTS_DIR), load_side(args.candidate, RESULTS_DIR))
    print(render(report))
    if args.out:
        Path(args.out).parent.mkdir(parents=True, exist_ok=True)
        Path(args.out).write_text(json.dumps(report, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
        print(f"\nwrote {args.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
