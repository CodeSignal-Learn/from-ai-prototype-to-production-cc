"""Run a dataset split through the assistant and score every result against the rubric.

    python3 -m evals.runner --dataset v1 --split development --client replay --label baseline
    python3 -m evals.runner --dataset v1 --split development --record --label baseline   # live, records
    python3 -m evals.runner --dataset v1 --split held_out --client replay --no-judge --label checks-only

Deterministic criteria (R1, R2, R5) are counted here. Judged criteria (R3, R4) are asked of the
judge in evals/judge.py for every result that carries a draft; a result without a draft has no
statements to judge and passes them. Every run writes results/evals/<run-id>/items.jsonl (one
row per case) and summary.json (recomputed from the rows), and names the dataset version, its
checksum, the client, and the versions of the code, prompts, model, and judge prompt that
produced it. With --record, the pipeline and the judge run live through a RecordingClient, so
the same run replays offline afterwards.
"""
import argparse
import dataclasses
import json
import sys
import time
from collections import Counter, defaultdict
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path

from support_assistant.config import Settings, load_settings
from support_assistant.knowledge import load_articles
from support_assistant.llm.client import LLMClient
from support_assistant.llm.errors import LLMFailed
from support_assistant.llm.factory import build_client
from support_assistant.llm.retry import call_with_retry
from support_assistant.models import Article
from support_assistant.pipeline import process_request, retry_policy
from support_assistant.version import versions

from .dataset import Case, build_manifest, load_cases
from .judge import judge_draft, judge_prompt_version
from .rubric import Rubric, load_rubric

ROOT = Path(__file__).resolve().parent.parent
RESULTS_DIR = ROOT / "results" / "evals"
SECURITY_REASONS = ("empty_draft", "draft_too_long", "unverifiable_promise", "ungrounded_number", "ungrounded_link")
NO_DRAFT = "no draft to judge"


@dataclass
class Item:
    id: str
    split: str
    kind: str
    tags: list
    expected_category: str
    expected_route: str
    expected_article: str | None
    category: str
    route: str
    article: str | None
    reasons: list
    confidence: float | None
    draft: str | None
    verdicts: dict
    evidence: dict
    forbidden_phrases: list
    judged: bool
    acceptable: bool | None
    seconds: float


def deterministic_verdicts(case: Case, category: str, route: str, reasons: list, draft: str | None) -> tuple[dict, dict, list]:
    verdicts, evidence = {}, {}
    verdicts["R1"] = "pass" if category == case.expected_category and route == case.expected_route else "fail"
    evidence["R1"] = f"got {category}/{route}, expected {case.expected_category}/{case.expected_route}"
    if route == case.expected_route:
        verdicts["R2"] = "pass"
    elif case.expected_route == "human_review":
        verdicts["R2"] = "missed"
    else:
        verdicts["R2"] = "over"
    evidence["R2"] = ", ".join(reasons) if reasons else "no escalation reason"
    tripped = [r for r in reasons if r in SECURITY_REASONS]
    forbidden = [phrase for phrase in case.must_not_mention if draft and phrase in draft.lower()]
    verdicts["R5"] = "fail" if tripped or forbidden else "pass"
    evidence["R5"] = "; ".join(tripped + [f"mentions {p!r}" for p in forbidden]) or "no commitment found"
    return verdicts, evidence, forbidden


def normalize(text: str) -> str:
    return " ".join(text.lower().split())


def score_case(case: Case, articles: list[Article], settings: Settings, client: LLMClient | None,
               judge: LLMClient | None, rubric: Rubric, sleep=time.sleep) -> Item:
    request = case.request
    started = time.perf_counter()
    result = process_request(request, articles, settings, client, sleep)
    verdicts, evidence, forbidden = deterministic_verdicts(case, result.category, result.route, result.reasons, result.draft)
    judged = True
    if result.draft is None:
        verdicts["R3"], verdicts["R4"] = "pass", "pass"
        evidence["R3"], evidence["R4"] = NO_DRAFT, NO_DRAFT
    elif judge is None:
        judged = False
    else:
        article = next((a for a in articles if a.slug == result.article), None)
        try:
            judgment = call_with_retry(lambda: judge_draft(judge, rubric, case, request, article, result.draft), retry_policy(settings), sleep)
        except LLMFailed as error:
            judged = False
            evidence["judge_error"] = str(error)
        else:
            verdicts.update(judgment.verdicts)
            evidence.update(judgment.evidence)
            evidence["judge_notes"] = judgment.notes
            quotes = judgment.evidence.get("R3", [])
            evidence["R3_quotes_in_draft"] = sum(1 for q in quotes if normalize(q) in normalize(result.draft))
            evidence["R3_quotes"] = len(quotes)
    acceptable = rubric.acceptable(verdicts) if judged else None
    return Item(
        id=case.id, split=case.split, kind=case.kind, tags=list(case.tags),
        expected_category=case.expected_category, expected_route=case.expected_route, expected_article=case.expected_article,
        category=result.category, route=result.route, article=result.article, reasons=list(result.reasons),
        confidence=result.confidence, draft=result.draft, verdicts=verdicts, evidence=evidence,
        forbidden_phrases=forbidden, judged=judged, acceptable=acceptable, seconds=round(time.perf_counter() - started, 3),
    )


def summarize(items: list[dict], rubric: Rubric) -> dict:
    """Everything a report needs, recomputed from the rows so a summary cannot be typed by hand."""
    criteria = {c.id: dict(Counter(item["verdicts"].get(c.id, "unjudged") for item in items)) for c in rubric.criteria}
    by_category = {}
    for category in sorted({item["expected_category"] for item in items}):
        subset = [item for item in items if item["expected_category"] == category]
        by_category[category] = {
            "cases": len(subset),
            "R1_pass": sum(item["verdicts"]["R1"] == "pass" for item in subset),
            "R2_missed": sum(item["verdicts"]["R2"] == "missed" for item in subset),
            "R2_over": sum(item["verdicts"]["R2"] == "over" for item in subset),
            "R3_fail": sum(item["verdicts"].get("R3") == "fail" for item in subset),
            "R4_not_pass": sum(item["verdicts"].get("R4") in ("partial", "fail") for item in subset),
            "R5_fail": sum(item["verdicts"]["R5"] == "fail" for item in subset),
            "acceptable": sum(bool(item["acceptable"]) for item in subset),
        }
    failures = []
    for item in items:
        for criterion in rubric.criteria:
            verdict = item["verdicts"].get(criterion.id)
            if verdict is None or verdict == "pass":
                continue
            failures.append({"id": item["id"], "criterion": criterion.id, "verdict": verdict, "evidence": item["evidence"].get(criterion.id)})
    judged = [item for item in items if item["judged"]]
    misquoted = [item["id"] for item in items
                 if item["evidence"].get("R3_quotes") and item["evidence"]["R3_quotes_in_draft"] < item["evidence"]["R3_quotes"]]
    return {
        "judge_quotes_not_in_draft": misquoted,
        "cases": len(items),
        "drafted": sum(1 for item in items if item["draft"]),
        "judged": len(judged),
        "unjudged": len(items) - len(judged),
        "acceptable": sum(bool(item["acceptable"]) for item in items),
        "acceptable_rate": round(sum(bool(item["acceptable"]) for item in judged) / len(judged), 3) if judged else None,
        "criteria": criteria,
        "article_correct": sum(1 for item in items if item["article"] == item["expected_article"]),
        "by_category": by_category,
        "by_tag": {
            tag: {"cases": n, "acceptable": sum(bool(item["acceptable"]) for item in items if tag in item["tags"])}
            for tag, n in sorted(Counter(tag for item in items for tag in item["tags"]).items())
        },
        "failures": failures,
        "median_seconds": sorted(item["seconds"] for item in items)[len(items) // 2] if items else None,
    }


def write_run(run_dir: Path, items: list[Item], summary: dict) -> None:
    run_dir.mkdir(parents=True, exist_ok=True)
    with (run_dir / "items.jsonl").open("w", encoding="utf-8") as handle:
        for item in items:
            handle.write(json.dumps(asdict(item), ensure_ascii=False) + "\n")
    (run_dir / "summary.json").write_text(json.dumps(summary, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def load_run(run_dir: Path) -> tuple[list[dict], dict]:
    items = [json.loads(line) for line in (run_dir / "items.jsonl").read_text(encoding="utf-8").splitlines() if line.strip()]
    return items, json.loads((run_dir / "summary.json").read_text(encoding="utf-8"))


def run(dataset: str, split: str, settings: Settings, client: LLMClient | None, judge: LLMClient | None,
        run_id: str, rubric: Rubric | None = None, results_dir: Path = RESULTS_DIR, sleep=time.sleep, log=print) -> dict:
    rubric = rubric or load_rubric()
    articles = load_articles(settings.knowledge_dir)
    cases = load_cases(dataset, split, {a.slug for a in articles})
    items = []
    for index, case in enumerate(cases, start=1):
        item = score_case(case, articles, settings, client, judge, rubric, sleep)
        items.append(item)
        flags = " ".join(f"{k}={v}" for k, v in item.verdicts.items() if v != "pass")
        log(f"[{index}/{len(cases)}] {case.id} {item.category}/{item.route} {flags or 'ok'}")
    rows = [asdict(item) for item in items]
    summary = {
        "run_id": run_id,
        "created_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "dataset": dataset,
        "dataset_sha256": build_manifest(dataset, load_cases(dataset, article_slugs={a.slug for a in articles}))["cases_sha256"],
        "split": split,
        "versions": versions(settings),
        "rubric_version": rubric.version,
        "judge": None if judge is None else {"model": settings.model, "prompt": judge_prompt_version(rubric)},
        **summarize(rows, rubric),
        "usage": {
            "pipeline": asdict_usage(client),
            "judge": asdict_usage(judge),
        },
    }
    write_run(results_dir / run_id, items, summary)
    return summary


def asdict_usage(client) -> dict | None:
    if client is None:
        return None
    usage = client.usage
    return {"calls": usage.calls, "input_tokens": usage.input_tokens, "output_tokens": usage.output_tokens}


def print_summary(summary: dict) -> None:
    print(f"\nrun {summary['run_id']}: {summary['cases']} cases from {summary['dataset']}/{summary['split']}, "
          f"{summary['drafted']} drafted, {summary['judged']} judged")
    for criterion, counts in summary["criteria"].items():
        print(f"  {criterion}: " + ", ".join(f"{verdict} {n}" for verdict, n in sorted(counts.items())))
    print(f"  article correct: {summary['article_correct']}/{summary['cases']}")
    print(f"  acceptable: {summary['acceptable']}/{summary['judged']} judged" + (f" ({summary['acceptable_rate']:.2f})" if summary["acceptable_rate"] is not None else ""))
    for category, row in summary["by_category"].items():
        print(f"  {category:<16} cases {row['cases']:>3}  R1 pass {row['R1_pass']:>3}  R2 missed {row['R2_missed']:>2} over {row['R2_over']:>2}  "
              f"R3 fail {row['R3_fail']:>2}  R4 not pass {row['R4_not_pass']:>2}  R5 fail {row['R5_fail']:>2}  acceptable {row['acceptable']:>3}")
    for name in ("pipeline", "judge"):
        usage = summary["usage"].get(name)
        if usage:
            print(f"  {name} usage: {usage['calls']} calls, {usage['input_tokens']} in, {usage['output_tokens']} out")


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--dataset", default="v1")
    parser.add_argument("--split", choices=("development", "held_out"), default="development")
    parser.add_argument("--client", choices=("live", "replay"), default=None, help="overrides ASSISTANT_LLM_CLIENT")
    parser.add_argument("--record", action="store_true", help="run live and record every completion for replay")
    parser.add_argument("--no-judge", action="store_true", help="deterministic criteria only")
    parser.add_argument("--label", required=True, help="run id suffix; the run is written to results/evals/<dataset>-<split>-<label>/")
    args = parser.parse_args(argv)

    settings = dataclasses.replace(load_settings(), mode="model", **({"llm_client": args.client} if args.client else {}))
    if args.record:
        from support_assistant.llm.live import LiveClient
        from support_assistant.llm.replay import RecordingClient
        settings = dataclasses.replace(settings, llm_client="live")
        client = RecordingClient(LiveClient(settings.model, settings.timeout_seconds), settings.recordings_dir)
        judge = None if args.no_judge else RecordingClient(LiveClient(settings.model, settings.timeout_seconds), settings.recordings_dir)
    else:
        client = build_client(settings)
        judge = None if args.no_judge else build_client(settings)
    run_id = f"{args.dataset}-{args.split}-{args.label}"
    summary = run(args.dataset, args.split, settings, client, judge, run_id)
    print_summary(summary)
    print(f"wrote results/evals/{run_id}/")
    return 0


if __name__ == "__main__":
    sys.exit(main())
