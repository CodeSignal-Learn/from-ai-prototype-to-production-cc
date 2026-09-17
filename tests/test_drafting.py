from support_assistant.drafting import compose_draft
from support_assistant.knowledge import find_article
from support_assistant.pipeline import process_request


def test_draft_greets_customer_by_first_name(make_request, articles):
    request = make_request("Refund status", "when will i get my refund", customer_name="Ada Lovelace")
    article = find_article(articles, "returns_refunds", request.text)
    assert compose_draft(request, article).startswith("Hi Ada,")


def test_draft_contains_article_summary(make_request, articles):
    request = make_request("Refund status", "when will i get my refund")
    article = find_article(articles, "returns_refunds", request.text)
    assert article.summary in compose_draft(request, article)


def test_result_is_never_sent(make_request, articles):
    request = make_request("Refund status", "when will i get my refund")
    result = process_request(request, articles)
    assert result.route == "draft"
    assert result.sent is False
