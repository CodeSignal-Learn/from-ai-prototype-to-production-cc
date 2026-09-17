import re

# Keyword rules that assign a category to a request. The category with the most
# keyword hits wins; on a tie, the category listed first wins, so returns_refunds
# is listed before orders_shipping (a return of a shipped order is a return).
# A request with no hits is "other".
CATEGORY_KEYWORDS: dict[str, tuple[str, ...]] = {
    "billing": ("invoice", "charged", "charge", "payment", "billing", "receipt", "double"),
    "account_access": ("password", "log in", "login", "locked out", "sign in", "reset", "two-factor"),
    "returns_refunds": ("return", "refund", "exchange", "send back"),
    "orders_shipping": (
        "shipping", "delivery", "delivered", "tracking", "shipped", "package",
        "where is my order", "order status",
    ),
    "product_issue": ("broken", "defective", "zipper", "leak", "leaks", "torn", "stopped working", "warranty"),
}

FALLBACK_CATEGORY = "other"


def contains_keyword(text: str, keyword: str) -> bool:
    """True when the keyword appears as whole words, so "reset" does not match "preset"
    but "locked out" and "shipping." still match."""
    return re.search(rf"\b{re.escape(keyword)}\b", text) is not None


def count_hits(text: str, keywords: tuple[str, ...]) -> int:
    return sum(1 for keyword in keywords if contains_keyword(text, keyword))


def classify(text: str) -> str:
    """Return the category whose keywords appear most often in the text."""
    best_category = FALLBACK_CATEGORY
    best_hits = 0
    for category, keywords in CATEGORY_KEYWORDS.items():
        hits = count_hits(text, keywords)
        if hits > best_hits:
            best_category = category
            best_hits = hits
    return best_category
