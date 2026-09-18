"""What the pipeline does when the model misbehaves. Time never passes for real here."""
import json

from support_assistant.config import Settings
from support_assistant.intake import load_requests
from support_assistant.llm.client import ScriptedClient
from support_assistant.llm.errors import LLMRateLimited, LLMTimeout, LLMUnavailable
from support_assistant.llm.replay import ReplayClient
from support_assistant.pipeline import CLASSIFICATION_UNAVAILABLE, DRAFT_UNAVAILABLE, process_batch, process_request

NO_SLEEP = lambda seconds: None  # noqa: E731


def verdict(category, confidence=0.9):
    return json.dumps({"category": category, "confidence": confidence, "reason": "scripted"})


def test_transient_timeout_is_retried_and_the_request_still_gets_a_draft(make_request, articles, model_settings):
    client = ScriptedClient([LLMTimeout("slow"), verdict("returns_refunds"), "Hi Test, five business days."])
    result = process_request(make_request("Refund", "where is my refund for the boots"), articles, model_settings, client, sleep=NO_SLEEP)
    assert result.route == "draft"
    assert result.draft.startswith("Hi Test")
    assert len(client.calls) == 3


def test_classification_that_keeps_failing_goes_to_a_person(make_request, articles, model_settings):
    client = ScriptedClient([LLMTimeout("1"), LLMUnavailable("2"), LLMRateLimited("3")])
    result = process_request(make_request("Refund", "where is my refund for the boots"), articles, model_settings, client, sleep=NO_SLEEP)
    assert result.route == "human_review"
    assert CLASSIFICATION_UNAVAILABLE in result.reasons
    assert result.category == "other"
    assert result.confidence is None
    assert result.draft is None
    assert result.sent is False


def test_drafting_that_keeps_failing_keeps_the_category_and_escalates(make_request, articles, model_settings):
    client = ScriptedClient([verdict("returns_refunds"), LLMTimeout("1"), LLMTimeout("2"), LLMTimeout("3")])
    result = process_request(make_request("Refund", "where is my refund for the boots"), articles, model_settings, client, sleep=NO_SLEEP)
    assert result.category == "returns_refunds"
    assert result.route == "human_review"
    assert result.reasons == [DRAFT_UNAVAILABLE]
    assert result.draft is None


def test_malformed_answer_is_asked_again_then_falls_back(make_request, articles, model_settings):
    client = ScriptedClient(["not json at all", "still not json", "nope"])
    result = process_request(make_request("Refund", "where is my refund for the boots"), articles, model_settings, client, sleep=NO_SLEEP)
    assert CLASSIFICATION_UNAVAILABLE in result.reasons
    assert len(client.calls) == 3


def test_retry_budget_comes_from_settings(make_request, articles):
    settings = Settings(mode="model", llm_client="replay", max_retries=0)
    client = ScriptedClient([LLMTimeout("once")])
    result = process_request(make_request("Refund", "where is my refund for the boots"), articles, settings, client, sleep=NO_SLEEP)
    assert CLASSIFICATION_UNAVAILABLE in result.reasons
    assert len(client.calls) == 1


def test_one_failing_request_does_not_stop_the_batch(articles, model_settings):
    requests = load_requests("data/trial.jsonl")[:3]
    client = ScriptedClient([
        verdict("billing"), "Draft one.",
        LLMTimeout("1"), LLMTimeout("2"), LLMTimeout("3"),
        verdict("account_access"), "Draft three.",
    ])
    results = process_batch(requests, articles, model_settings, client, sleep=NO_SLEEP)
    assert [r.id for r in results] == [r.id for r in requests]
    assert results[0].route == "draft"
    assert CLASSIFICATION_UNAVAILABLE in results[1].reasons
    assert results[2].route == "draft"


def test_replay_client_injects_failures_before_serving(tmp_path):
    client = ReplayClient(tmp_path, model="fake", failures=[LLMTimeout("injected")])
    try:
        client.complete("s", "u", 10)
    except LLMTimeout:
        pass
    else:
        raise AssertionError("the injected failure was not raised")
