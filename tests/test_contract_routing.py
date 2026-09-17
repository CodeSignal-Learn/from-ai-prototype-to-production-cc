"""Routing contract: real requests from the August batch and the category each must get.

These cases come from docs/spec-order-routing.md and from the batch review. They exercise
multi-word keywords, punctuation next to keywords, and tie-breaking, which the unit tests
in test_routing.py do not.
"""
from pathlib import Path

import pytest

from support_assistant.intake import load_requests
from support_assistant.routing import classify

REQUESTS = {request.id: request for request in load_requests(Path(__file__).resolve().parent.parent / "data" / "requests.jsonl")}

EXPECTED = {
    "REQ-1001": "billing",          # "charged twice"
    "REQ-1002": "billing",          # "invoice"
    "REQ-1008": "account_access",   # "log in" (two words)
    "REQ-1009": "account_access",   # "locked out" (two words)
    "REQ-1012": "account_access",   # "two-factor" (hyphen)
    "REQ-1014": "orders_shipping",  # "where is my order", "tracking"
    "REQ-1017": "orders_shipping",  # "order status", "shipped?"
    "REQ-1020": "orders_shipping",  # "shipping." (punctuation)
    "REQ-1021": "orders_shipping",  # "tracking", "package"
    "REQ-1023": "returns_refunds",  # tie with orders_shipping, returns win
    "REQ-1028": "returns_refunds",  # tie with orders_shipping, returns win
    "REQ-1030": "product_issue",    # "leaks"
    "REQ-1031": "product_issue",    # "stopped working" (two words)
    "REQ-1035": "other",            # gift wrapping, no keywords
    "REQ-1040": "other",            # wholesale, no keywords
}


@pytest.mark.parametrize("request_id, expected", sorted(EXPECTED.items()))
def test_batch_request_routes_to_expected_category(request_id, expected):
    assert classify(REQUESTS[request_id].text) == expected
