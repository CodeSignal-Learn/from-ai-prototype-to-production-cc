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
from .telemetry.events import EventSink, text_fingerprint
from .telemetry.trace import Trace
from .version import versions

CLASSIFICATION_UNAVAILABLE = "classification_unavailable"
DRAFT_UNAVAILABLE = "draft_unavailable"
ARTICLE_DOES_NOT_ANSWER = "article_does_not_answer"
NO_ARTICLE_NAMED = "no_article_named"


def retry_policy(settings: Settings) -> RetryPolicy:
    return RetryPolicy(max_retries=settings.max_retries, base_delay_seconds=settings.retry_base_delay_seconds)


def process_request(
    request: SupportRequest,
    articles: list[Article],
    settings: Settings,
    client: LLMClient | None = None,
    sleep=time.sleep,
    sink: EventSink | None = None,
    clock=time.perf_counter,
    now=None,
) -> Result:
    """Classify, look up, draft, and route one request. Nothing is sent.

    settings.mode "rules" is the keyword assistant and needs no client. Mode "model" asks the
    client for the category and the draft; every escalation rule still applies to its output.
    A model call that fails after the retry policy is exhausted never fails the request: the
    request goes to a person with a reason that says which step was unavailable.

    Every step emits an event on the sink (in memory when none is given) under one trace id, with
    its duration and the tokens it used. Events carry no customer or draft text.
    """
    trace = Trace(request.id, sink if sink is not None else EventSink(), clock, **({"now": now} if now else {}))
    metered = trace.meter(client)
    trace.emit("request", "received", channel=request.channel, flags=list(request.flags), body=text_fingerprint(request.body))
    confidence = None
    reasons: list[str] = []
    chosen: Article | None = None
    named_article = False
    variant = settings.prompt_variant
    try:
        if settings.mode == "model":
            if client is None:
                raise ValueError("model mode needs an LLM client")
            policy = retry_policy(settings)
            with trace.step("classify", mode="model", variant=variant) as outcome:
                try:
                    verdict = call_with_retry(lambda: model.classify(metered, request, variant, articles), policy, sleep)
                    category = verdict.category
                    confidence = verdict.confidence
                    # v2 names the article; it is used only if it exists and belongs to the category.
                    chosen = next((a for a in articles if a.slug == verdict.article and a.category == category), None)
                    named_article = verdict.article is not None
                    outcome.attrs.update(category=category, confidence=confidence, named_article=verdict.article)
                except LLMFailed as error:
                    category = "other"
                    reasons.append(CLASSIFICATION_UNAVAILABLE)
                    outcome.status = "unavailable"
                    outcome.attrs.update(category=category, attempts=error.attempts, last_error=type(error.last_error).__name__)
        else:
            with trace.step("classify", mode="rules") as outcome:
                category = classify(request.text)
                outcome.attrs["category"] = category
        with trace.step("lookup") as outcome:
            article = chosen or find_article(articles, category, request.text)
            outcome.attrs.update(article=article.slug if article else None, method="model" if chosen else "keyword")
        reasons += escalation_reasons(request, category, article)
        if confidence is not None and confidence < settings.confidence_threshold:
            reasons.append("low_confidence")
        if settings.mode == "model" and variant == "v2" and settings.draft_policy == "skip_unnamed" and not named_article and article is not None:
            # The classifier saw every article and named none. Drafting from the keyword fallback almost
            # always ends in a decline; the policy saves that call and sends the request to a person.
            reasons.append(NO_ARTICLE_NAMED)
        route = decide_route(reasons)
        draft = None
        if route == DRAFT and article:
            if settings.mode == "model":
                with trace.step("draft", mode="model", variant=variant) as outcome:
                    try:
                        draft = call_with_retry(lambda: model.draft(metered, request, article, variant), policy, sleep)
                    except LLMFailed as error:
                        reasons.append(DRAFT_UNAVAILABLE)
                        route = decide_route(reasons)
                        outcome.status = "unavailable"
                        outcome.attrs.update(attempts=error.attempts, last_error=type(error.last_error).__name__)
                    else:
                        if draft is None:
                            # v2: the model said the article does not answer. No deferral is drafted;
                            # the request goes to a person as an escalation, not as a draft to review.
                            reasons.append(ARTICLE_DOES_NOT_ANSWER)
                            route = decide_route(reasons)
                            outcome.status = "declined"
                        else:
                            outcome.attrs["draft"] = text_fingerprint(draft)
                with trace.step("checks") as outcome:
                    problems = check_draft(draft, article, request) if draft is not None else []
                    if problems:
                        reasons += problems
                        route = decide_route(reasons)
                        outcome.status = "flagged"
                    outcome.attrs["problems"] = problems
            else:
                with trace.step("draft", mode="rules") as outcome:
                    draft = compose_draft(request, article)
                    outcome.attrs["draft"] = text_fingerprint(draft)
        result = Result(
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
    except Exception as error:
        trace.emit("request", "failed", trace.elapsed_ms(), error=type(error).__name__, versions=versions(settings))
        raise
    status = "flagged" if any(r in ("unverifiable_promise", "ungrounded_number", "ungrounded_link", "draft_too_long", "empty_draft") for r in reasons) \
        else "escalated" if route != DRAFT else "ok"
    trace.emit("request", status, trace.elapsed_ms(), category=category, route=route, reasons=list(reasons), drafted=draft is not None,
               article=result.article, versions=result.versions, **trace.total_usage.as_attrs())
    return result


def process_batch(
    requests: list[SupportRequest],
    articles: list[Article],
    settings: Settings,
    client: LLMClient | None = None,
    sleep=time.sleep,
    sink: EventSink | None = None,
) -> list[Result]:
    """Process requests with at most settings.concurrency in flight; results keep input order.

    Concurrency is bounded on purpose: the model service rate-limits, and unbounded parallelism
    turns a slow batch into a failing one. One sink receives every request's events.
    """
    sink = sink if sink is not None else EventSink(settings.events_file)
    if settings.concurrency <= 1 or len(requests) <= 1:
        return [process_request(request, articles, settings, client, sleep, sink) for request in requests]
    with ThreadPoolExecutor(max_workers=settings.concurrency) as pool:
        return list(pool.map(lambda request: process_request(request, articles, settings, client, sleep, sink), requests))
