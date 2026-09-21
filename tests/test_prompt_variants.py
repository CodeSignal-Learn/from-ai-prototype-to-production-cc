"""The v2 candidate prompts change two contracts: the classifier may name the article, and the
drafter may decline. Both are checked by the pipeline, never trusted. Scripted clients only."""
import json

import pytest

from support_assistant import model
from support_assistant.config import Settings, validate
from support_assistant.llm.client import ScriptedClient
from support_assistant.llm.replay import recording_key
from support_assistant.pipeline import ARTICLE_DOES_NOT_ANSWER, process_request
from support_assistant.security import InvalidVerdict, validate_verdict
from support_assistant.version import prompt_version, versions


def verdict(category, article=None, confidence=0.95):
    return json.dumps({"category": category, "confidence": confidence, "article": article, "reason": "scripted"})


@pytest.fixture
def v2():
    return Settings(mode="model", llm_client="replay", prompt_variant="v2")


def test_v1_prompts_are_unchanged_and_v2_differs():
    assert prompt_version("v1") != prompt_version("v2")
    assert model.prompts("v1") == (model.CLASSIFY_SYSTEM, model.DRAFT_SYSTEM)
    with pytest.raises(ValueError):
        model.prompts("v3")


def test_versions_carry_the_variant(v2):
    stamped = versions(v2)
    assert stamped["prompt_variant"] == "v2"
    assert stamped["prompt"] == prompt_version("v2") != versions(Settings(mode="model", llm_client="replay"))["prompt"]


def test_the_variant_is_validated():
    with pytest.raises(ValueError, match="PROMPT_VARIANT"):
        validate(Settings(prompt_variant="v9"))


def test_v2_classifier_sees_the_article_list_and_the_pipeline_uses_its_choice(make_request, articles, v2):
    client = ScriptedClient([verdict("account_access", "password-reset"), "Hi Test, choose Forgot password on the sign-in page.\n\nFernwood Outfitters Support"])
    request = make_request("Cannot get in", "every time i try the site says my details are wrong")
    result = process_request(request, articles, v2, client)
    assert "<articles>" in client.calls[0]["user"] and "password-reset:" in client.calls[0]["user"]
    assert result.article == "password-reset"        # keyword lookup alone would pick account-merge
    assert result.route == "draft"


def test_an_article_outside_the_category_is_ignored(make_request, articles, v2):
    client = ScriptedClient([verdict("account_access", "shipping-times"), "Hi Test, thanks.\n\nFernwood Outfitters Support"])
    result = process_request(make_request("Cannot get in", "the site says my details are wrong"), articles, v2, client)
    assert result.article == "account-merge"          # falls back to the keyword lookup


def test_an_unknown_article_slug_is_ignored(make_request, articles, v2):
    client = ScriptedClient([verdict("billing", "not-an-article"), "Hi Test, thanks.\n\nFernwood Outfitters Support"])
    result = process_request(make_request("Charged twice", "two identical amounts left my account"), articles, v2, client)
    assert result.article == "billing-and-invoices"


def test_a_non_string_article_is_a_malformed_verdict():
    with pytest.raises(InvalidVerdict, match="article"):
        validate_verdict({"category": "billing", "confidence": 0.9, "article": 7})


def test_no_answer_routes_to_a_person_without_a_draft(make_request, articles, v2):
    client = ScriptedClient([verdict("orders_shipping", "order-tracking"), "NO_ANSWER"])
    result = process_request(make_request("New address", "how do i make sure my order goes to my new address"), articles, v2, client)
    assert result.route == "human_review"
    assert ARTICLE_DOES_NOT_ANSWER in result.reasons
    assert result.draft is None
    assert len(client.calls) == 2


def test_no_answer_in_a_fence_still_counts(make_request, articles, v2):
    client = ScriptedClient([verdict("billing", "billing-and-invoices"), "```\nNO_ANSWER\n```"])
    result = process_request(make_request("Tax", "why was i charged sales tax"), articles, v2, client)
    assert ARTICLE_DOES_NOT_ANSWER in result.reasons and result.draft is None


def test_v1_never_interprets_the_marker(make_request, articles):
    v1 = Settings(mode="model", llm_client="replay")
    client = ScriptedClient([verdict("billing"), "NO_ANSWER"])
    result = process_request(make_request("Tax", "why was i charged sales tax"), articles, v1, client)
    assert result.draft == "NO_ANSWER" and ARTICLE_DOES_NOT_ANSWER not in result.reasons
    assert "<articles>" not in client.calls[0]["user"]


def test_v2_draft_prompt_forbids_capability_claims_and_inferences():
    assert "Do not describe what a specialist" in model.DRAFT_SYSTEM_V2
    assert "NO_ANSWER" in model.DRAFT_SYSTEM_V2
    assert model.DATA_RULE in model.DRAFT_SYSTEM_V2 and model.DATA_RULE in model.CLASSIFY_SYSTEM_V2


def test_the_recording_salt_separates_repeats_and_an_empty_salt_keeps_old_keys():
    plain = recording_key("m", "s", "u", 5)
    assert recording_key("m", "s", "u", 5, "") == plain
    assert recording_key("m", "s", "u", 5, "repeat-1") != plain
    assert recording_key("m", "s", "u", 5, "repeat-1") != recording_key("m", "s", "u", 5, "repeat-2")
