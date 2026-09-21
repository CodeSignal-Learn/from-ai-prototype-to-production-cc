import time
from concurrent.futures import ThreadPoolExecutor

from . import model
from .config import Settings
from .drafting import compose_draft
from .escalation import DRAFT, decide_route, escalation_reasons
from .knowledge import find_article
from .llm.client import LLMClient
from .llm.errors import LLMFailed
from .llm.retry import RetryPolicy, call_with_retry
from .models import Article, Result, SupportRequest
from .routing import classify
from .security import check_draft
from .version import versions

CLASSIFICATION_UNAVAILABLE = "classification_unavailable"
DRAFT_UNAVAILABLE = "draft_unavailable"
ARTICLE_DOES_NOT_ANSWER = "article_does_not_answer"


def retry_policy(settings: Settings) -> RetryPolicy:
    return RetryPolicy(max_retries=settings.max_retries, base_delay_seconds=settings.retry_base_delay_seconds)


def process_request(
    request: SupportRequest,
    articles: list[Article],
    settings: Settings,
    client: LLMClient | None = None,
    sleep=time.sleep,
) -> Result:
    """Classify, look up, draft, and route one request. Nothing is sent.

    settings.mode "rules" is the keyword assistant and needs no client. Mode "model" asks the
    client for the category and the draft; every escalation rule still applies to its output.
    A model call that fails after the retry policy is exhausted never fails the request: the
    request goes to a person with a reason that says which step was unavailable.
    """
    confidence = None
    reasons: list[str] = []
    chosen: Article | None = None
    variant = settings.prompt_variant
    if settings.mode == "model":
        if client is None:
            raise ValueError("model mode needs an LLM client")
        policy = retry_policy(settings)
        try:
            verdict = call_with_retry(lambda: model.classify(client, request, variant, articles), policy, sleep)
            category = verdict.category
            confidence = verdict.confidence
            # v2 names the article; it is used only if it exists and belongs to the category.
            chosen = next((a for a in articles if a.slug == verdict.article and a.category == category), None)
        except LLMFailed:
            category = "other"
            reasons.append(CLASSIFICATION_UNAVAILABLE)
    else:
        category = classify(request.text)
    article = chosen or find_article(articles, category, request.text)
    reasons += escalation_reasons(request, category, article)
    if confidence is not None and confidence < settings.confidence_threshold:
        reasons.append("low_confidence")
    route = decide_route(reasons)
    draft = None
    if route == DRAFT and article:
        if settings.mode == "model":
            try:
                draft = call_with_retry(lambda: model.draft(client, request, article, variant), policy, sleep)
            except LLMFailed:
                reasons.append(DRAFT_UNAVAILABLE)
                route = decide_route(reasons)
            else:
                if draft is None:
                    # v2: the model said the article does not answer. No deferral is drafted;
                    # the request goes to a person as an escalation, not as a draft to review.
                    reasons.append(ARTICLE_DOES_NOT_ANSWER)
                    route = decide_route(reasons)
                else:
                    problems = check_draft(draft, article, request)
                    if problems:
                        reasons += problems
                        route = decide_route(reasons)
        else:
            draft = compose_draft(request, article)
    return Result(
        id=request.id,
        category=category,
        route=route,
        reasons=reasons,
        article=article.slug if article else None,
        draft=draft,
        sent=False,
        confidence=confidence,
        versions=versions(settings),
    )


def process_batch(
    requests: list[SupportRequest],
    articles: list[Article],
    settings: Settings,
    client: LLMClient | None = None,
    sleep=time.sleep,
) -> list[Result]:
    """Process requests with at most settings.concurrency in flight; results keep input order.

    Concurrency is bounded on purpose: the model service rate-limits, and unbounded parallelism
    turns a slow batch into a failing one.
    """
    if settings.concurrency <= 1 or len(requests) <= 1:
        return [process_request(request, articles, settings, client, sleep) for request in requests]
    with ThreadPoolExecutor(max_workers=settings.concurrency) as pool:
        return list(pool.map(lambda request: process_request(request, articles, settings, client, sleep), requests))
