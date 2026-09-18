from .drafting import compose_draft
from .escalation import DRAFT, decide_route, escalation_reasons
from .knowledge import find_article
from .models import Article, Result, SupportRequest
from .routing import classify


MODES = ("rules", "model")


def process_request(request: SupportRequest, articles: list[Article], mode: str = "rules") -> Result:
    """Classify, look up, draft, and route one request. Nothing is sent.

    mode "rules" is the keyword assistant. mode "model" is the POC prototype (see ADR 001).
    """
    if mode not in MODES:
        raise ValueError(f"unknown mode {mode!r}; expected one of {MODES}")
    confidence = None
    if mode == "model":
        from . import model

        verdict = model.classify(request.text)
        category = verdict["category"]
        confidence = verdict["confidence"]
    else:
        category = classify(request.text)
    article = find_article(articles, category, request.text)
    reasons = escalation_reasons(request, category, article)
    if confidence is not None and confidence < model.CONFIDENCE_THRESHOLD:
        reasons.append("low_confidence")
    route = decide_route(reasons)
    draft = None
    if route == DRAFT and article:
        draft = model.draft(request, article) if mode == "model" else compose_draft(request, article)
    return Result(
        id=request.id,
        category=category,
        route=route,
        reasons=reasons,
        article=article.slug if article else None,
        draft=draft,
        sent=False,
        confidence=confidence,
    )


def process_batch(requests: list[SupportRequest], articles: list[Article], mode: str = "rules") -> list[Result]:
    return [process_request(request, articles, mode=mode) for request in requests]
