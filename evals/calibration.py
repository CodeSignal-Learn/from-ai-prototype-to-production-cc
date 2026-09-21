"""How far the model judge can be trusted: agreement with human judgments on the same drafts.

    python3 -m evals.calibration --run v1-development-baseline --human evals/datasets/v1/human_judgments.jsonl

Human judgments are written by a reviewer who read each draft next to its article and applied
R3 and R4 from evals/rubric.md. Each row names the run and the case and carries a checksum of
the draft it judged, so a judgment can never be compared against a different draft. The output
is agreement and Cohen's kappa per criterion, the confusion table, and every disagreement with
both sides' evidence. Nothing here changes a verdict; the point is to know, before trusting the
judge on cases nobody read, where it agrees with a person and where it does not.
"""
import argparse
import hashlib
import json
from collections import Counter
from pathlib import Path

from .rubric import load_rubric
from .runner import RESULTS_DIR, load_run


def draft_checksum(draft: str) -> str:
    return hashlib.sha256(draft.encode("utf-8")).hexdigest()[:12]


def load_human(path: Path) -> list[dict]:
    return [json.loads(line) for line in Path(path).read_text(encoding="utf-8").splitlines() if line.strip()]


def cohens_kappa(pairs: list[tuple[str, str]]) -> float | None:
    """Agreement beyond chance between two raters over the same items; None with fewer than two items."""
    if len(pairs) < 2:
        return None
    observed = sum(1 for a, b in pairs if a == b) / len(pairs)
    labels = {label for pair in pairs for label in pair}
    first = Counter(a for a, _ in pairs)
    second = Counter(b for _, b in pairs)
    expected = sum(first[label] / len(pairs) * second[label] / len(pairs) for label in labels)
    if expected == 1.0:
        return 1.0
    return round((observed - expected) / (1 - expected), 3)


def compare(items: list[dict], human: list[dict], criteria: tuple[str, ...] = ("R3", "R4")) -> dict:
    by_id = {item["id"]: item for item in items}
    report = {"judged_by_both": 0, "skipped": [], "criteria": {}}
    pairs = {criterion: [] for criterion in criteria}
    disagreements = {criterion: [] for criterion in criteria}
    for row in human:
        item = by_id.get(row["id"])
        if item is None or not item.get("draft"):
            report["skipped"].append({"id": row["id"], "reason": "not in run or no draft"})
            continue
        if draft_checksum(item["draft"]) != row["draft_sha"]:
            report["skipped"].append({"id": row["id"], "reason": "draft changed since the human judgment"})
            continue
        if not item.get("judged"):
            report["skipped"].append({"id": row["id"], "reason": "judge did not return a verdict"})
            continue
        report["judged_by_both"] += 1
        for criterion in criteria:
            machine, person = item["verdicts"][criterion], row[criterion]
            pairs[criterion].append((person, machine))
            if machine != person:
                disagreements[criterion].append({
                    "id": row["id"], "human": person, "judge": machine,
                    "human_evidence": row.get(f"{criterion}_evidence", ""),
                    "judge_evidence": item["evidence"].get(criterion),
                })
    for criterion in criteria:
        matched = pairs[criterion]
        confusion = Counter(matched)
        report["criteria"][criterion] = {
            "items": len(matched),
            "agreement": round(sum(1 for a, b in matched if a == b) / len(matched), 3) if matched else None,
            "kappa": cohens_kappa(matched),
            "confusion": {f"human={a} judge={b}": n for (a, b), n in sorted(confusion.items())},
            "judge_stricter": sum(1 for a, b in matched if rank(b) > rank(a)),
            "judge_lenient": sum(1 for a, b in matched if rank(b) < rank(a)),
            "disagreements": disagreements[criterion],
        }
    return report


def rank(verdict: str) -> int:
    """Severity order, so 'stricter' and 'more lenient' mean the same thing for both criteria."""
    return {"pass": 0, "partial": 1, "fail": 2}[verdict]


def render(report: dict) -> str:
    lines = [f"drafts judged by both: {report['judged_by_both']}"]
    for skipped in report["skipped"]:
        lines.append(f"skipped {skipped['id']}: {skipped['reason']}")
    for criterion, block in report["criteria"].items():
        lines.append(f"\n{criterion}: {block['items']} drafts, agreement {block['agreement']}, kappa {block['kappa']}, "
                     f"judge stricter {block['judge_stricter']}, judge more lenient {block['judge_lenient']}")
        for cell, n in block["confusion"].items():
            lines.append(f"  {cell}: {n}")
        for d in block["disagreements"]:
            lines.append(f"  disagreement {d['id']}: human {d['human']} vs judge {d['judge']}")
            lines.append(f"    human: {d['human_evidence']}")
            lines.append(f"    judge: {d['judge_evidence']}")
    return "\n".join(lines)


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--run", required=True, help="run id under results/evals/")
    parser.add_argument("--human", required=True, help="JSONL of human judgments")
    parser.add_argument("--out", default=None, help="write the report as JSON here as well")
    args = parser.parse_args(argv)
    items, _ = load_run(RESULTS_DIR / args.run)
    rubric = load_rubric()
    report = compare(items, load_human(args.human), tuple(c.id for c in rubric.judged))
    print(render(report))
    if args.out:
        Path(args.out).write_text(json.dumps(report, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
        print(f"\nwrote {args.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
