"""Record the model's answers for a set of requests so the replay client can serve them offline.

Usage: python3 scripts/record.py data/requests.jsonl data/trial.jsonl

Runs model mode through a live client wrapped in a RecordingClient, so every prompt the pipeline
sends gets a recording in the configured recordings folder. Recordings are keyed by the exact
prompt; change a prompt and this must run again. Costs real money; the summary prints usage.
"""
import dataclasses
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from support_assistant.config import load_settings  # noqa: E402
from support_assistant.intake import load_requests  # noqa: E402
from support_assistant.knowledge import load_articles  # noqa: E402
from support_assistant.llm.live import LiveClient  # noqa: E402
from support_assistant.llm.replay import RecordingClient  # noqa: E402
from support_assistant.pipeline import process_batch  # noqa: E402


def main(paths):
    settings = dataclasses.replace(load_settings(), mode="model", llm_client="live")
    client = RecordingClient(LiveClient(settings.model, settings.timeout_seconds), settings.recordings_dir)
    articles = load_articles(settings.knowledge_dir)
    before = len(list(Path(settings.recordings_dir).glob("*.json")))
    started = time.perf_counter()
    for path in paths:
        requests = load_requests(path)
        results = process_batch(requests, articles, settings, client)
        drafted = sum(1 for r in results if r.draft)
        print(f"{path}: {len(results)} requests, {drafted} drafts")
    after = len(list(Path(settings.recordings_dir).glob("*.json")))
    usage = client.usage
    print(f"recordings: {before} -> {after} in {settings.recordings_dir}")
    print(f"calls: {usage.calls}  input tokens: {usage.input_tokens}  output tokens: {usage.output_tokens}  seconds: {time.perf_counter() - started:.1f}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:] or ["data/requests.jsonl", "data/trial.jsonl"]))
