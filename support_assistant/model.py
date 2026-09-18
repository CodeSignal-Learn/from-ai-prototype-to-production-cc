"""Model-backed classification and drafting, through the LLMClient interface.

Instructions go in the system prompt; the customer's text goes in the user message. Answers are
parsed here and checked by the caller.
"""
import json

from .llm.client import LLMClient
from .llm.errors import LLMMalformed
from .models import Article, SupportRequest

CATEGORIES = ("billing", "account_access", "returns_refunds", "orders_shipping", "product_issue", "other")

CLASSIFY_SYSTEM = (
    "You classify customer support requests for Fernwood Outfitters, an outdoor gear store.\n"
    "Categories: " + ", ".join(CATEGORIES) + ".\n"
    "billing: charges, invoices, receipts, payments. account_access: signing in, passwords, "
    "two-factor, merging or changing accounts. returns_refunds: returning or exchanging items, "
    "refund status, store credit. orders_shipping: where an order is, delivery times, tracking, "
    "address changes. product_issue: defects, warranty, product care. other: anything else.\n"
    "Answer with JSON only, in the form "
    '{"category": "billing", "confidence": 0.9, "reason": "one sentence"}. '
    "confidence is your probability, between 0 and 1, that the category is right."
)

DRAFT_SYSTEM = (
    "You write replies for Fernwood Outfitters customer support. A support agent will review "
    "the reply before it is sent.\n"
    "Use only facts stated in the article you are given. If the article does not answer the "
    "customer's question, say that a specialist will follow up; do not invent policy, prices, or "
    "dates. Do not promise refunds, credits, replacements, or any action. Keep it under 120 words "
    "and sign off as Fernwood Outfitters Support."
)


def parse_json_answer(text: str) -> dict:
    """Parse the model's JSON, tolerating a Markdown code fence around it.

    An answer that still does not parse is a malformed completion: the caller's retry policy
    decides whether to ask again, and the pipeline falls back to a person after that.
    """
    body = text.strip()
    if body.startswith("```"):
        body = body.split("\n", 1)[1] if "\n" in body else ""
        body = body.rsplit("```", 1)[0]
    try:
        parsed = json.loads(body)
    except json.JSONDecodeError as error:
        raise LLMMalformed(f"answer is not JSON: {error}") from error
    if not isinstance(parsed, dict):
        raise LLMMalformed("answer is JSON but not an object")
    return parsed


def classify(client: LLMClient, text: str) -> dict:
    """Return the model's category, confidence, and reason for a request text."""
    completion = client.complete(CLASSIFY_SYSTEM, "Request:\n" + text, max_tokens=200)
    return parse_json_answer(completion.text)


def draft(client: LLMClient, request: SupportRequest, article: Article) -> str:
    """Write a reply grounded in the article."""
    user = (
        "Article: " + article.title + "\n" + article.body + "\n\n"
        "Customer name: " + request.customer_name + "\n"
        "Request:\n" + request.text + "\n\nReply:"
    )
    return client.complete(DRAFT_SYSTEM, user, max_tokens=400).text
