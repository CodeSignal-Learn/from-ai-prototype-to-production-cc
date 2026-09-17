# Fernwood support-request assistant

## What this is
An internal tool that drafts replies to written support requests for a human to review.
Rules-based: keyword routing in `support_assistant/routing.py`, knowledge lookup in
`knowledge.py`, template drafts in `drafting.py`, escalation rules in `escalation.py`.
`pipeline.py` ties them together; `cli.py` runs a JSONL batch.

## Boundaries
- Drafts are never sent. `Result.sent` stays `False` and nothing in this codebase makes network
  calls. Do not add sending, webhooks, or notifications.
- Do not add dependencies. The project is standard-library only apart from pytest.
- Keep `Result` fields as they are: `id`, `category`, `route`, `reasons`, `article`, `draft`, `sent`.
- Keep intake normalization (trim, collapse whitespace, lowercase). Routing keywords are
  lowercase and depend on it.
- Categories are `billing`, `account_access`, `returns_refunds`, `orders_shipping`,
  `product_issue`, `other`. `other` always goes to human review.
- Knowledge articles in `kb/` are the support team's content. Do not edit them for a code change.

## How to verify a change
```bash
python3 -m pytest
python3 -m support_assistant.cli data/requests.jsonl
```
Run both after any implementation change and report the actual results. The test suite does
not cover every routing keyword or every escalation rule; when a change touches one, add a test
for it and say which cases remain unverified.

## Working agreements
- Propose a plan and list the files you will touch before editing.
- Make the smallest change that meets the request. Mention anything out of scope you noticed
  instead of fixing it.
