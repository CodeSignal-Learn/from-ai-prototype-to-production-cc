# Keyword rules that assign a category to a request. The first category with the
# highest number of keyword hits wins; a request with no hits is "other".
CATEGORY_KEYWORDS: dict[str, tuple[str, ...]] = {
    "billing": ("invoice", "charged", "charge", "payment", "billing", "receipt", "double"),
    "account_access": ("password", "log in", "login", "locked out", "sign in", "reset", "two-factor"),
    "orders_shipping": ("shipping", "delivery", "delivered"),
    "returns_refunds": ("return", "refund", "exchange", "send back"),
    "product_issue": ("broken", "defective", "zipper", "leak", "torn", "stopped working", "warranty"),
}

FALLBACK_CATEGORY = "other"


def count_hits(text: str, keywords: tuple[str, ...]) -> int:
    return sum(1 for keyword in keywords if keyword in text)


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
