"""Model mode with a scripted client. No test here contacts the API."""
import json

import pytest

from support_assistant.config import Settings
from support_assistant.llm.client import ScriptedClient
from support_assistant.llm.errors import LLMMalformed
from support_assistant.model import parse_json_answer
from support_assistant.pipeline import process_request


def verdict(category, confidence):
    return json.dumps({"category": category, "confidence": confidence, "reason": "scripted"})


def test_confident_classification_gets_a_model_draft(make_request, articles, model_settings):
    client = ScriptedClient([verdict("returns_refunds", 0.92), "Hi Ada, your refund arrives within five business days."])
    request = make_request("Where is my money", "you received the boots back two weeks ago and my card shows nothing", customer_name="Ada Lovelace")
    result = process_request(request, articles, model_settings, client)
    assert result.category == "returns_refunds"
    assert result.route == "draft"
    assert result.draft.startswith("Hi Ada")
    assert result.confidence == 0.92
    assert result.sent is False
    assert len(client.calls) == 2


def test_low_confidence_goes_to_a_person(make_request, articles, model_settings):
    client = ScriptedClient([verdict("billing", 0.4)])
    request = make_request("Money question", "something about an amount on my statement that looks odd")
    result = process_request(request, articles, model_settings, client)
    assert result.route == "human_review"
    assert "low_confidence" in result.reasons
    assert result.draft is None
    assert len(client.calls) == 1


def test_threshold_comes_from_settings(make_request, articles):
    strict = Settings(mode="model", llm_client="replay", confidence_threshold=0.95)
    client = ScriptedClient([verdict("billing", 0.9)])
    request = make_request("Money question", "an amount on my statement looks odd to me")
    assert "low_confidence" in process_request(request, articles, strict, client).reasons


def test_guard_rules_still_apply_in_model_mode(make_request, articles, model_settings):
    client = ScriptedClient([verdict("billing", 0.99)])
    request = make_request("Last warning", "refund this or my attorney will file in small claims")
    result = process_request(request, articles, model_settings, client)
    assert result.route == "human_review"
    assert "legal_threat" in result.reasons
    assert result.draft is None


def test_customer_text_is_not_in_the_system_prompt(make_request, articles, model_settings):
    client = ScriptedClient([verdict("billing", 0.9), "Hi Test, thanks."])
    request = make_request("Charged twice", "two identical amounts left my account for one order")
    process_request(request, articles, model_settings, client)
    for call in client.calls:
        assert "identical amounts" not in call["system"]
        assert "identical amounts" in call["user"]


def test_rules_mode_has_no_confidence(make_request, articles, rules_settings):
    request = make_request("Refund status", "when will i get my refund")
    result = process_request(request, articles, rules_settings)
    assert result.confidence is None
    assert result.route == "draft"


def test_model_mode_without_a_client_is_rejected(make_request, articles, model_settings):
    with pytest.raises(ValueError):
        process_request(make_request("Hi", "hello there friend"), articles, model_settings)


def test_fenced_json_answer_is_parsed():
    fenced = '```json\n{"category": "billing", "confidence": 0.95, "reason": "duplicate charge"}\n```'
    assert parse_json_answer(fenced) == {"category": "billing", "confidence": 0.95, "reason": "duplicate charge"}


def test_unparseable_answer_is_malformed():
    with pytest.raises(LLMMalformed):
        parse_json_answer("Sure! This looks like a billing question.")
