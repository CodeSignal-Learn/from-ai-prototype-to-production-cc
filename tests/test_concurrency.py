import json

from support_assistant.config import Settings
from support_assistant.intake import load_requests
from support_assistant.llm.client import ScriptedClient
from support_assistant.pipeline import process_batch

REQUESTS = load_requests("data/requests.jsonl")


def test_concurrent_batch_matches_sequential_batch_in_rules_mode(articles):
    sequential = process_batch(REQUESTS, articles, Settings(mode="rules", concurrency=1))
    concurrent = process_batch(REQUESTS, articles, Settings(mode="rules", concurrency=8))
    assert [r.id for r in concurrent] == [r.id for r in REQUESTS]
    assert concurrent == sequential


def test_concurrent_batch_keeps_order_in_model_mode(articles):
    requests = REQUESTS[:6]
    # Threads reach the script in any order, so every call gets the same answer: a verdict for
    # classify, and plain text the draft step accepts as it is.
    answer = json.dumps({"category": "billing", "confidence": 0.9, "reason": "x"})
    client = ScriptedClient([answer] * 12)
    results = process_batch(requests, articles, Settings(mode="model", llm_client="replay", concurrency=3), client, sleep=lambda s: None)
    assert [r.id for r in results] == [r.id for r in requests]
    assert client.usage.calls == 12


def test_replay_latency_is_simulated_with_the_injected_sleep(tmp_path):
    from support_assistant.llm.replay import RecordingClient, ReplayClient

    RecordingClient(ScriptedClient(["answer"], model="m"), tmp_path).complete("s", "u", 5)
    slept = []
    client = ReplayClient(tmp_path, model="m", latency_seconds=2.0, sleep=slept.append)
    client.complete("s", "u", 5)
    assert slept == [2.0]
