"""Run the trial set through the assistant and compare with the sponsor's labels.

Usage:
    python3 scripts/run_trial.py --mode rules
    python3 scripts/run_trial.py --mode model --input-rate 1.00 --output-rate 5.00

Writes results/trial-<mode>.jsonl and prints the gate numbers. Rates are dollars per million
tokens for the model in use and are supplied by the operator, never guessed by the code.
"""
import argparse
import json
import statistics
import sys
import time
from dataclasses import asdict
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

import dataclasses  # noqa: E402

from support_assistant.config import load_settings  # noqa: E402
from support_assistant.intake import load_requests  # noqa: E402
from support_assistant.knowledge import load_articles  # noqa: E402
from support_assistant.llm.factory import build_client  # noqa: E402
from support_assistant.pipeline import process_request  # noqa: E402

GUARD_WORDS = ("hostile", "legal", "injection")


def load_labels(path):
    return {json.loads(line)["id"]: json.loads(line) for line in Path(path).read_text().splitlines() if line.strip()}


def main(argv=None):
    parser = argparse.ArgumentParser()
    parser.add_argument("--mode", choices=["rules", "model"], default="rules")
    parser.add_argument("--client", choices=["live", "replay"], default=None, help="overrides ASSISTANT_LLM_CLIENT")
    parser.add_argument("--requests", default=str(ROOT / "data" / "trial.jsonl"))
    parser.add_argument("--labels", default=str(ROOT / "data" / "trial_labels.jsonl"))
    parser.add_argument("--kb", default=str(ROOT / "kb"))
    parser.add_argument("--out", default=None, help="results JSONL; defaults to results/trial-<mode>.jsonl")
    parser.add_argument("--input-rate", type=float, default=None, help="dollars per million input tokens")
    parser.add_argument("--output-rate", type=float, default=None, help="dollars per million output tokens")
    args = parser.parse_args(argv)

    settings = dataclasses.replace(load_settings(), mode=args.mode, **({"llm_client": args.client} if args.client else {}))
    client = build_client(settings) if settings.mode == "model" else None
    requests = load_requests(args.requests)
    labels = load_labels(args.labels)
    articles = load_articles(args.kb)
    out_path = Path(args.out) if args.out else ROOT / "results" / f"trial-{args.mode}.jsonl"
    out_path.parent.mkdir(parents=True, exist_ok=True)

    rows = []
    for request in requests:
        started = time.perf_counter()
        result = process_request(request, articles, settings, client)
        elapsed = time.perf_counter() - started
        label = labels[request.id]
        row = asdict(result)
        row.update(
            expected_category=label["expected_category"],
            expected_route=label["expected_route"],
            category_correct=result.category == label["expected_category"],
            route_correct=result.route == label["expected_route"],
            seconds=round(elapsed, 3),
        )
        rows.append(row)

    with out_path.open("w", encoding="utf-8") as handle:
        for row in rows:
            handle.write(json.dumps(row, ensure_ascii=False) + "\n")

    total = len(rows)
    category_accuracy = sum(r["category_correct"] for r in rows) / total
    route_accuracy = sum(r["route_correct"] for r in rows) / total
    unsafe = [r["id"] for r in rows if r["expected_route"] == "human_review" and r["route"] == "draft"
              and any(word in labels[r["id"]]["note"].lower() for word in GUARD_WORDS)]
    over_escalated = [r["id"] for r in rows if r["expected_route"] == "draft" and r["route"] == "human_review"]
    wrong_category = [f"{r['id']} {r['category']}->{r['expected_category']}" for r in rows if not r["category_correct"]]
    median_seconds = statistics.median(r["seconds"] for r in rows)

    print(f"mode: {args.mode}")
    print(f"requests: {total}")
    print(f"category accuracy: {category_accuracy:.2f}")
    print(f"route accuracy: {route_accuracy:.2f}")
    print(f"wrong categories: {', '.join(wrong_category) if wrong_category else 'none'}")
    print(f"unsafe drafts (guard cases drafted): {', '.join(unsafe) if unsafe else 'none'}")
    print(f"over-escalated (expected draft, got human review): {', '.join(over_escalated) if over_escalated else 'none'}")
    print(f"median seconds per request: {median_seconds:.3f}")

    if client is not None:
        usage = client.usage
        print(f"client: {settings.llm_client}  model: {settings.model}")
        print(f"input tokens: {usage.input_tokens}  output tokens: {usage.output_tokens}  calls: {usage.calls}")
        if args.input_rate is not None and args.output_rate is not None:
            cost = usage.input_tokens / 1e6 * args.input_rate + usage.output_tokens / 1e6 * args.output_rate
            print(f"estimated cost: ${cost:.4f} total, ${cost / total:.4f} per request")
        else:
            print("estimated cost: not computed (pass --input-rate and --output-rate)")
    print(f"wrote {out_path.relative_to(ROOT)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
