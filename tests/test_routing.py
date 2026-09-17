from support_assistant.routing import classify


def test_billing_request_routes_to_billing():
    assert classify("i was charged twice for one order") == "billing"


def test_password_request_routes_to_account_access():
    assert classify("i need to reset my password") == "account_access"


def test_refund_request_routes_to_returns_refunds():
    assert classify("my refund has not arrived") == "returns_refunds"


def test_defect_request_routes_to_product_issue():
    assert classify("the zipper on my jacket is broken") == "product_issue"


def test_unrelated_request_routes_to_other():
    assert classify("what colors does the ridge jacket come in") == "other"


def test_tracking_request_routes_to_orders_shipping():
    assert classify("the tracking number still shows label created") == "orders_shipping"


def test_missing_package_routes_to_orders_shipping():
    assert classify("my package has been sitting at a carrier hub for a week") == "orders_shipping"


def test_return_of_a_delivered_order_prefers_returns():
    assert classify("the carrier shows it delivered to you but no refund has appeared") == "returns_refunds"
