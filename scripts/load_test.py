"""Send requests to a running assistant API and report latency and throughput.

Usage:
    python3 scripts/load_test.py --base-url http://127.0.0.1:8000 --requests data/requests.jsonl \
        --concurrency 1 4 8 --count 24 --out results/load-<label>.json

Each concurrency level sends `count` requests to POST /requests with that many in flight and
records every response time. Numbers are wall-clock from this client; run it against a server
started with the configuration you want to measure, and say what that configuration was. The
service key is read from ASSISTANT_API_KEY (or --api-key) and sent as X-API-Key.
"""
import argparse
import json
import os
import statistics
import sys
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import httpx

ROOT = Path(__file__).resolve().parent.parent


def percentile(values, fraction):
    ordered = sorted(values)
    index = min(len(ordered) - 1, max(0, round(fraction * (len(ordered) - 1))))
    return ordered[index]


def one_call(client, base_url, record):
    started = time.perf_counter()
    try:
        response = client.post(f"{base_url}/requests", json=record, timeout=120.0)
        ok = response.status_code == 200
    except httpx.HTTPError:
        ok = False
    return time.perf_counter() - started, ok


def run_level(base_url, records, concurrency, count, api_key):
    chosen = [records[i % len(records)] for i in range(count)]
    started = time.perf_counter()
    with httpx.Client(headers={"X-API-Key": api_key}) as client, ThreadPoolExecutor(max_workers=concurrency) as pool:
        outcomes = list(pool.map(lambda record: one_call(client, base_url, record), chosen))
    wall = time.perf_counter() - started
    latencies = [seconds for seconds, _ in outcomes]
    errors = sum(1 for _, ok in outcomes if not ok)
    return {
        "concurrency": concurrency,
        "requests": count,
        "errors": errors,
        "wall_seconds": round(wall, 3),
        "throughput_per_second": round(count / wall, 3),
        "p50_seconds": round(statistics.median(latencies), 3),
        "p95_seconds": round(percentile(latencies, 0.95), 3),
        "p99_seconds": round(percentile(latencies, 0.99), 3),
        "max_seconds": round(max(latencies), 3),
    }


def main(argv=None):
    parser = argparse.ArgumentParser()
    parser.add_argument("--base-url", default="http://127.0.0.1:8000")
    parser.add_argument("--requests", default=str(ROOT / "data" / "requests.jsonl"))
    parser.add_argument("--concurrency", type=int, nargs="+", default=[1, 4, 8])
    parser.add_argument("--count", type=int, default=24)
    parser.add_argument("--out", default=None)
    parser.add_argument("--api-key", default=os.environ.get("ASSISTANT_API_KEY"))
    args = parser.parse_args(argv)
    if not args.api_key:
        sys.exit("set ASSISTANT_API_KEY or pass --api-key; the server refuses requests without it")
    if args.count < 1 or any(level < 1 for level in args.concurrency):
        sys.exit("--count and every --concurrency level must be at least 1")

    records = [json.loads(line) for line in Path(args.requests).read_text().splitlines() if line.strip()]
    if not records:
        sys.exit(f"no requests in {args.requests}")
    with httpx.Client() as client:
        health = client.get(f"{args.base_url}/health", timeout=10.0).json()
    print("server:", json.dumps(health))
    levels = []
    for concurrency in args.concurrency:
        level = run_level(args.base_url, records, concurrency, args.count, args.api_key)
        levels.append(level)
        print(f"concurrency {level['concurrency']:>2}: {level['requests']} requests in {level['wall_seconds']:.1f} s, "
              f"{level['throughput_per_second']:.2f} req/s, p50 {level['p50_seconds']:.2f} s, "
              f"p95 {level['p95_seconds']:.2f} s, p99 {level['p99_seconds']:.2f} s, errors {level['errors']}")
    report = {"server": health, "levels": levels}
    if args.out:
        Path(args.out).parent.mkdir(parents=True, exist_ok=True)
        Path(args.out).write_text(json.dumps(report, indent=2) + "\n")
        print(f"wrote {args.out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
