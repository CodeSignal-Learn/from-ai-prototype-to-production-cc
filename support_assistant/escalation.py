from .models import Article, SupportRequest

# Requests that match any of these are sent to a person instead of receiving a draft.
HOSTILE_TERMS = ("unacceptable", "furious", "disgusted", "worst experience", "scam")

DRAFT = "draft"
HUMAN_REVIEW = "human_review"


def escalation_reasons(request: SupportRequest, category: str, article: Article | None) -> list[str]:
    """List the reasons a request needs a human, or an empty list if a draft is fine."""
    reasons = []
    if category == "other":
        reasons.append("unknown_category")
    if article is None:
        reasons.append("no_reference_article")
    if any(term in request.text for term in HOSTILE_TERMS):
        reasons.append("hostile_language")
    return reasons


def decide_route(reasons: list[str]) -> str:
    return HUMAN_REVIEW if reasons else DRAFT
