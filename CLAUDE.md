# Fernwood support-request assistant

## What this is
An internal tool that drafts replies to written support requests for a human to review.
Two modes share one pipeline (`pipeline.py`, selected with `--mode`):
- `rules`: keyword routing in `support_assistant/routing.py`, template drafts in `drafting.py`.
- `model`: the POC prototype from `docs/adr-001-prototype-slice.md`. `model.py` asks a language
  model for the category and confidence, and for a draft written from the selected article.
Knowledge lookup in `knowledge.py` and escalation rules in `escalation.py` apply in both modes.
`cli.py` runs a JSONL batch; `scripts/run_trial.py` measures a mode against the trial labels.

## Boundaries
- Drafts are never sent. `Result.sent` stays `False`. The only network calls in this codebase are
  the model calls in model mode; do not add sending, webhooks, or notifications.
- Dependencies are pinned in `requirements.txt` (`anthropic`, `pytest`). Do not add others.
- Keep `Result` fields as they are: `id`, `category`, `route`, `reasons`, `article`, `draft`,
  `sent`, `confidence` (`None` in rules mode).
- The model's output is advisory. It never sends, never chooses the route on its own, and every
  escalation rule applies to its output too. Drafts come from the selected article only.
- Model mode needs `ANTHROPIC_API_KEY` in the environment. Tests must never call the API; fake
  `model.classify` and `model.draft` instead.
- Keep intake normalization (trim, collapse whitespace, lowercase). Routing keywords are
  lowercase and depend on it.
- Categories are `billing`, `account_access`, `returns_refunds`, `orders_shipping`,
  `product_issue`, `other`. `other` always goes to human review.
- Knowledge articles in `kb/` are the support team's content. Do not edit them for a code change.

## How to verify a change
```bash
python3 -m pytest
python3 -m support_assistant.cli data/requests.jsonl
python3 -m support_assistant.cli data/requests.jsonl --mode model
```
Run both after any implementation change and report the actual results. The test suite does
not cover every routing keyword or every escalation rule; when a change touches one, add a test
for it and say which cases remain unverified.

## Working agreements
- Propose a plan and list the files you will touch before editing.
- Make the smallest change that meets the request. Mention anything out of scope you noticed
  instead of fixing it.
