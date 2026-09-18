"""Boundaries around untrusted text: what customers write, and what the model answers.

Customer text is data. It can contain instructions aimed at the assistant, card numbers, or
markup that would break the prompt. Model output is also untrusted: it must fit the shape we
asked for and a draft may not commit the company to anything the article does not say.
"""
import re
from dataclasses import dataclass

from .models import Article, SupportRequest

CATEGORIES = ("billing", "account_access", "returns_refunds", "orders_shipping", "product_issue", "other")

# Phrases that address the assistant rather than describe a problem.
INSTRUCTION_PATTERNS = tuple(re.compile(p, re.IGNORECASE) for p in (
    r"\bignore (all |any |the )?(previous|prior|above|earlier) (instructions|prompts?|rules)\b",
    r"\bdisregard (all |any |the )?(previous|prior|above|earlier|your) (instructions|prompts?|rules)\b",
    r"\byou are now (a|an|the|my)\b",
    r"\bact as (a|an|the) \w+ (manager|agent|admin|administrator|system)\b",
    r"\b(system|developer) prompt\b",
    r"\bnew instructions?:",
    r"\bmark (this |the |my )?order[^.]{0,40}\bas (delivered|resolved|refunded|shipped|cancelled|canceled)\b",
    r"\bconfirm (that )?(a |the )?(full )?(refund|credit|replacement) (has been|was|is) (issued|processed|approved|sent)\b",
))

CARD_NUMBER = re.compile(r"\b(?:\d[ -]?){13,19}\b")
SENSITIVE_PLACEHOLDER = "[card number removed]"

# A draft may not claim that something has already been done or will be done by us.
PROMISE_PATTERNS = tuple(re.compile(p, re.IGNORECASE) for p in (
    r"\b(i|we)('ve| have) (issued|refunded|processed|cancell?ed|shipped|sent|applied|updated|changed|reset|merged)\b",
    r"\b(has|have) been (refunded|issued|cancell?ed|processed|shipped|updated|reset|merged|approved)\b",
    r"\bwill be (refunded|credited|replaced|cancell?ed|reshipped)\b",
    r"\b(i|we) (will|'ll) (refund|credit|replace|cancel|reship|waive)\b",
))
NUMBER = re.compile(r"\$?\d[\d,]*(?:\.\d+)?")
URL = re.compile(r"https?://\S+", re.IGNORECASE)
MAX_DRAFT_CHARS = 1200


def detect_instruction(text: str) -> bool:
    """True when the text tells the assistant what to do instead of describing a problem."""
    return any(pattern.search(text) for pattern in INSTRUCTION_PATTERNS)


def mask_sensitive(text: str) -> tuple[str, bool]:
    """Replace card-like digit runs. Returns the masked text and whether anything was masked."""
    masked, count = CARD_NUMBER.subn(SENSITIVE_PLACEHOLDER, text)
    return masked, count > 0


def escape_tag(text: str, tag: str) -> str:
    """Stop customer text from closing the tag we wrap it in."""
    return text.replace(f"</{tag}>", f"<\\/{tag}>").replace(f"<{tag}", f"<\\{tag}")


@dataclass(frozen=True)
class Verdict:
    category: str
    confidence: float
    reason: str


class InvalidVerdict(ValueError):
    """The model's classification does not fit the contract."""


def validate_verdict(parsed: dict) -> Verdict:
    category = parsed.get("category")
    confidence = parsed.get("confidence")
    if category not in CATEGORIES:
        raise InvalidVerdict(f"category {category!r} is not one of {CATEGORIES}")
    if isinstance(confidence, bool) or not isinstance(confidence, (int, float)):
        raise InvalidVerdict(f"confidence {confidence!r} is not a number")
    if not 0.0 <= float(confidence) <= 1.0:
        raise InvalidVerdict(f"confidence {confidence} is outside 0..1")
    reason = parsed.get("reason", "")
    return Verdict(category=category, confidence=float(confidence), reason=str(reason)[:300])


def check_draft(draft: str, article: Article, request: SupportRequest) -> list[str]:
    """Deterministic checks a draft must pass before it reaches the review queue."""
    problems = []
    if not draft.strip():
        problems.append("empty_draft")
        return problems
    if len(draft) > MAX_DRAFT_CHARS:
        problems.append("draft_too_long")
    if any(pattern.search(draft) for pattern in PROMISE_PATTERNS):
        problems.append("unverifiable_promise")
    allowed_numbers = set(NUMBER.findall(article.body)) | set(NUMBER.findall(request.text))
    if any(number not in allowed_numbers for number in NUMBER.findall(draft)):
        problems.append("ungrounded_number")
    allowed_urls = set(URL.findall(article.body))
    if any(url not in allowed_urls for url in URL.findall(draft)):
        problems.append("ungrounded_link")
    return problems
