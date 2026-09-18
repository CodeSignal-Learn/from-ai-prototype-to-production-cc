from . import model
from .config import Settings
from .drafting import compose_draft
from .escalation import DRAFT, decide_route, escalation_reasons
from .knowledge import find_article
from .llm.client import LLMClient
from .models import Article, Result, SupportRequest
from .routing import classify


def process_request(
    request: SupportRequest,
    articles: list[Article],
    settings: Settings,
    client: LLMClient | None = None,
) -> Result:
    """Classify, look up, draft, and route one request. Nothing is sent.

    settings.mode "rules" is the keyword assistant and needs no client. Mode "model" asks the
    client for the category and the draft; every escalation rule still applies to its output.
    """
    confidence = None
    if settings.mode == "model":
        if client is None:
            raise ValueError("model mode needs an LLM client")
        verdict = model.classify(client, request.text)
        category = verdict["category"]
        confidence = verdict["confidence"]
    else:
        category = classify(request.text)
    article = find_article(articles, category, request.text)
    reasons = escalation_reasons(request, category, article)
    if confidence is not None and confidence < settings.confidence_threshold:
        reasons.append("low_confidence")
    route = decide_route(reasons)
    draft = None
    if route == DRAFT and article:
        draft = model.draft(client, request, article) if settings.mode == "model" else compose_draft(request, article)
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


def process_batch(
    requests: list[SupportRequest],
    articles: list[Article],
    settings: Settings,
    client: LLMClient | None = None,
) -> list[Result]:
    return [process_request(request, articles, settings, client) for request in requests]
