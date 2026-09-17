import argparse
import json
from collections import Counter
from dataclasses import asdict
from pathlib import Path

from .intake import load_requests
from .knowledge import load_articles
from .pipeline import process_batch

DEFAULT_KB = Path(__file__).resolve().parent.parent / "kb"


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
    parser.add_argument("--kb", default=str(DEFAULT_KB), help="folder of knowledge-base articles")
    parser.add_argument("--out", help="where to write results as JSONL")
    args = parser.parse_args(argv)

    requests = load_requests(args.requests)
    articles = load_articles(args.kb)
    results = process_batch(requests, articles)

    for result in results:
        reasons = f" ({', '.join(result.reasons)})" if result.reasons else ""
        print(f"{result.id}  {result.category:<16} {result.route}{reasons}")
    print()
    print(summarize(results))

    if args.out:
        out_path = Path(args.out)
        out_path.parent.mkdir(parents=True, exist_ok=True)
        with out_path.open("w", encoding="utf-8") as handle:
            for result in results:
                handle.write(json.dumps(asdict(result)) + "\n")
        print(f"\nWrote {len(results)} results to {out_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
