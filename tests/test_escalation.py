from support_assistant.escalation import escalation_reasons


def test_one_word_body_is_insufficient_information(make_request, articles):
    request = make_request("Help", "help")
    assert "insufficient_information" in escalation_reasons(request, "other", None)


def test_short_body_with_a_category_still_escalates(make_request, articles):
    request = make_request("Refund", "refund please")
    reasons = escalation_reasons(request, "returns_refunds", articles[0])
    assert reasons == ["insufficient_information"]


def test_normal_body_is_not_insufficient(make_request, articles):
    request = make_request("Refund status", "when will i get my refund for order 48102")
    assert "insufficient_information" not in escalation_reasons(request, "returns_refunds", articles[0])


def test_legal_threat_escalates(make_request, articles):
    request = make_request("Charge dispute", "refund this or my lawyer will be in touch")
    assert "legal_threat" in escalation_reasons(request, "billing", articles[0])
