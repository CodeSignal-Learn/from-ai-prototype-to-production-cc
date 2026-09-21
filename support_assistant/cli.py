import argparse
import dataclasses
import json
from collections import Counter
from dataclasses import asdict
from pathlib import Path

from .config import load_settings
from .intake import load_requests
from .knowledge import load_articles
from .llm.factory import build_client
from .pipeline import process_batch


def summarize(results) -> str:
    by_category = Counter(result.category for result in results)
    by_route = Counter(result.route for result in results)
    lines = [f"Processed {len(results)} requests", "", "By category:"]
    lines += [f"  {category:<16} {count:>3}" for category, count in sorted(by_category.items())]
    lines += ["", "By route:"]
    lines += [f"  {route:<16} {count:>3}" for route, count in sorted(by_route.items())]
    return "\n".join(lines)


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description="Draft replies to support requests for human review.")
    parser.add_argument("requests", help="JSONL file with one support request per line")
    parser.add_argument("--kb", default=None, help="folder of knowledge-base articles (default: ASSISTANT_KNOWLEDGE_DIR)")
    parser.add_argument("--out", help="where to write results as JSONL")
    parser.add_argument("--mode", choices=["rules", "model"], default=None, help="overrides ASSISTANT_MODE")
    parser.add_argument("--client", choices=["live", "replay"], default=None, help="overrides ASSISTANT_LLM_CLIENT")
    parser.add_argument("--resume", action="store_true", help="skip requests already present in --out and append the rest")
    parser.add_argument("--concurrency", type=int, default=None, help="overrides ASSISTANT_CONCURRENCY")
    parser.add_argument("--events", default=None, help="JSONL event log to append to (overrides ASSISTANT_EVENTS_FILE)")
    args = parser.parse_args(argv)
    if args.resume and not args.out:
        parser.error("--resume needs --out")

    settings = load_settings()
    overrides = {name: value for name, value in (("mode", args.mode), ("llm_client", args.client), ("knowledge_dir", args.kb), ("concurrency", args.concurrency), ("events_file", args.events)) if value}
    for name in ("knowledge_dir", "events_file"):
        if name in overrides:
            overrides[name] = Path(overrides[name])
    settings = dataclasses.replace(settings, **overrides)

    rejected: list = []
    requests = load_requests(args.requests, rejected)
    for line_number, reason in rejected:
        print(f"Rejected line {line_number}: {reason}")
    done_ids = set()
    if args.resume and Path(args.out).exists():
        with Path(args.out).open(encoding="utf-8") as handle:
            done_ids = {json.loads(line)["id"] for line in handle if line.strip()}
        requests = [request for request in requests if request.id not in done_ids]
        print(f"Resuming: {len(done_ids)} already done, {len(requests)} to process")
    articles = load_articles(settings.knowledge_dir)
    client = build_client(settings) if settings.mode == "model" else None
    results = process_batch(requests, articles, settings, client)

    for result in results:
        reasons = f" ({', '.join(result.reasons)})" if result.reasons else ""
        print(f"{result.id}  {result.category:<16} {result.route}{reasons}")
    print()
    print(summarize(results))
    if client is not None:
        print(f"\nModel calls: {client.usage.calls}, input tokens: {client.usage.input_tokens}, output tokens: {client.usage.output_tokens}")
    if settings.events_file:
        print(f"Events appended to {settings.events_file}")

    if args.out:
        out_path = Path(args.out)
        out_path.parent.mkdir(parents=True, exist_ok=True)
        with out_path.open("a" if args.resume else "w", encoding="utf-8") as handle:
            for result in results:
                handle.write(json.dumps(asdict(result)) + "\n")
        print(f"\nWrote {len(results)} results to {out_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
