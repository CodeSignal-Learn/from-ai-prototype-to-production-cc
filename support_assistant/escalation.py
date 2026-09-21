from .intake import SENSITIVE_MASKED
from .models import Article, SupportRequest
from .security import detect_instruction

# Requests that match any of these are sent to a person instead of receiving a draft.
HOSTILE_TERMS = ("unacceptable", "furious", "disgusted", "worst experience", "scam")

# Threats of legal action always go to a person, whatever the category.
LEGAL_TERMS = ("lawyer", "attorney", "legal action", "small claims", "sue you")

# A body this short cannot be answered from an article; a person has to ask what is wrong.
MIN_BODY_WORDS = 3

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
    if len(request.body.split()) < MIN_BODY_WORDS:
        reasons.append("insufficient_information")
    if any(term in request.text for term in LEGAL_TERMS):
        reasons.append("legal_threat")
    if detect_instruction(request.text):
        reasons.append("instruction_to_assistant")
    if "oversized" in request.flags:
        reasons.append("oversized_request")
    if SENSITIVE_MASKED in request.flags:
        # The number is already masked; a person still has to answer, and tell the customer not
        # to send card numbers. A template or model draft cannot do that.
        reasons.append("sensitive_data")
    return reasons


def decide_route(reasons: list[str]) -> str:
    return HUMAN_REVIEW if reasons else DRAFT
