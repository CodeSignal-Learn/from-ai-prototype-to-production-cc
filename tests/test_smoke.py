from support_assistant.routing import classify


def test_whole_word_matching_still_routes_password_requests():
    assert classify("password reset") == "account_access"
