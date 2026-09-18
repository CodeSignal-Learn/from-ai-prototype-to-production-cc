"""Model-backed classification and drafting for the POC (ADR 001).

Prototype code: the model name and threshold are constants, calls have no timeout or retry,
prompts are built by string concatenation, and the model's JSON answer is trusted as returned.
"""
import json

from anthropic import Anthropic

from .models import Article, SupportRequest

MODEL = "claude-haiku-4-5"
CONFIDENCE_THRESHOLD = 0.6
CATEGORIES = ("billing", "account_access", "returns_refunds", "orders_shipping", "product_issue", "other")

# Token usage for the trial report, accumulated across every call in the process.
USAGE = {"input_tokens": 0, "output_tokens": 0, "calls": 0}

client = Anthropic()


def ask(prompt: str, max_tokens: int) -> str:
    response = client.messages.create(
        model=MODEL,
        max_tokens=max_tokens,
        messages=[{"role": "user", "content": prompt}],
    )
    USAGE["input_tokens"] += response.usage.input_tokens
    USAGE["output_tokens"] += response.usage.output_tokens
    USAGE["calls"] += 1
    return response.content[0].text


def classify(text: str) -> dict:
    """Return the model's category, confidence, and reason for a request text."""
    prompt = (
        "You classify customer support requests for Fernwood Outfitters, an outdoor gear store.\n"
        "Categories: " + ", ".join(CATEGORIES) + ".\n"
        "billing: charges, invoices, receipts, payments. account_access: signing in, passwords, "
        "two-factor, merging or changing accounts. returns_refunds: returning or exchanging items, "
        "refund status, store credit. orders_shipping: where an order is, delivery times, tracking, "
        "address changes. product_issue: defects, warranty, product care. other: anything else.\n"
        "Answer with JSON only, in the form "
        '{"category": "billing", "confidence": 0.9, "reason": "one sentence"}. '
        "confidence is your probability, between 0 and 1, that the category is right.\n\n"
        "Request:\n" + text
    )
    return json.loads(ask(prompt, 200))


def draft(request: SupportRequest, article: Article) -> str:
    """Write a reply grounded in the article. A support agent reviews it before anything is sent."""
    prompt = (
        "You write replies for Fernwood Outfitters customer support. A support agent will review "
        "the reply before it is sent.\n"
        "Use only facts stated in the article below. If the article does not answer the customer's "
        "question, say that a specialist will follow up; do not invent policy, prices, or dates. "
        "Do not promise refunds, credits, replacements, or any action. Keep it under 120 words and "
        "sign off as Fernwood Outfitters Support.\n\n"
        "Article: " + article.title + "\n" + article.body + "\n\n"
        "Customer name: " + request.customer_name + "\n"
        "Request:\n" + request.text + "\n\nReply:"
    )
    return ask(prompt, 400)
