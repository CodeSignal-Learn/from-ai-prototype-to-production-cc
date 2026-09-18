"""Model mode with the model calls faked. No test here contacts the API."""
import pytest

from support_assistant.pipeline import process_request


@pytest.fixture
def fake_model(monkeypatch):
    monkeypatch.setenv("ANTHROPIC_API_KEY", "test-key-never-used")
    from support_assistant import model

    def install(category, confidence, reply="Drafted reply."):
        monkeypatch.setattr(model, "classify", lambda text: {"category": category, "confidence": confidence, "reason": "fake"})
        monkeypatch.setattr(model, "draft", lambda request, article: reply)

    return install


def test_confident_classification_gets_a_model_draft(fake_model, make_request, articles):
    fake_model("returns_refunds", 0.92, reply="Hi Ada, your refund arrives within five business days.")
    request = make_request("Where is my money", "you received the boots back two weeks ago and my card shows nothing", customer_name="Ada Lovelace")
    result = process_request(request, articles, mode="model")
    assert result.category == "returns_refunds"
    assert result.route == "draft"
    assert result.draft.startswith("Hi Ada")
    assert result.confidence == 0.92
    assert result.sent is False


def test_low_confidence_goes_to_a_person(fake_model, make_request, articles):
    fake_model("billing", 0.4)
    request = make_request("Money question", "something about an amount on my statement that looks odd")
    result = process_request(request, articles, mode="model")
    assert result.route == "human_review"
    assert "low_confidence" in result.reasons
    assert result.draft is None


def test_guard_rules_still_apply_in_model_mode(fake_model, make_request, articles):
    fake_model("billing", 0.99)
    request = make_request("Last warning", "refund this or my attorney will file in small claims")
    result = process_request(request, articles, mode="model")
    assert result.route == "human_review"
    assert "legal_threat" in result.reasons
    assert result.draft is None


def test_rules_mode_has_no_confidence(make_request, articles):
    request = make_request("Refund status", "when will i get my refund")
    result = process_request(request, articles, mode="rules")
    assert result.confidence is None
    assert result.route == "draft"


def test_unknown_mode_is_rejected(make_request, articles):
    with pytest.raises(ValueError):
        process_request(make_request("Hi", "hello there friend"), articles, mode="magic")
