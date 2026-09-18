# Fernwood support-request assistant

## What this is
An internal tool that drafts replies to written support requests for a human to review.
Two modes share one pipeline (`pipeline.py`, selected with `--mode`):
- `rules`: keyword routing in `support_assistant/routing.py`, template drafts in `drafting.py`.
- `model`: `model.py` asks a language model for the category and confidence, and for a draft
  written from the selected article, through the `LLMClient` interface in `support_assistant/llm/`
  (`LiveClient` on the SDK, `ReplayClient` on recordings, `ScriptedClient` for tests).
Knowledge lookup in `knowledge.py` and escalation rules in `escalation.py` apply in both modes.
Settings come from `ASSISTANT_*` environment variables through `config.py` (ADR 002).
`cli.py` runs a JSONL batch with bounded concurrency; `api.py` serves the same pipeline over
HTTP; `scripts/run_trial.py` measures a mode against the trial labels; `scripts/load_test.py`
measures the API. Recordings for the replay client live in `fixtures/recordings/` and are
refreshed with `scripts/record.py` whenever a prompt changes.

## Boundaries
- Drafts are never sent. `Result.sent` stays `False`. The only network calls in this codebase are
  the model calls in model mode; do not add sending, webhooks, or notifications.
- Dependencies are pinned in `requirements.txt` (`anthropic`, `fastapi`, `uvicorn`, `httpx`, `pytest`). Do not add others.
- The API is served only with `ASSISTANT_API_KEY` set; `POST /requests` and `POST /batches`
  require it in `X-API-Key`, `GET /health` is open. Do not add an endpoint that takes customer
  text without the key check.
- Keep `Result` fields as they are: `id`, `category`, `route`, `reasons`, `article`, `draft`,
  `sent`, `confidence` (`None` in rules mode), `versions` (what produced the result).
- The model's output is advisory. It never sends, never chooses the route on its own, and every
  escalation rule applies to its output too. Drafts come from the selected article only.
- Only `llm/live.py` touches the Anthropic SDK; credentials are the SDK's business, not ours. Tests never call the API: use `ScriptedClient` or `ReplayClient`.
- Configuration is read once in `config.py`. Do not read environment variables anywhere else.
- Keep intake normalization (trim, collapse whitespace, lowercase). Routing keywords are
  lowercase and depend on it.
- Categories are `billing`, `account_access`, `returns_refunds`, `orders_shipping`,
  `product_issue`, `other`. `other` always goes to human review.
- Knowledge articles in `kb/` are the support team's content. Do not edit them for a code change.

## How to verify a change
```bash
python3 -m pytest
python3 -m support_assistant.cli data/requests.jsonl
python3 -m support_assistant.cli data/requests.jsonl --mode model --client replay
```
Model-mode checks run on the replay client. Never run live calls in tests or submission checks.
Run both after any implementation change and report the actual results. The test suite does
not cover every routing keyword or every escalation rule; when a change touches one, add a test
for it and say which cases remain unverified.

## Working agreements
- Propose a plan and list the files you will touch before editing.
- Make the smallest change that meets the request. Mention anything out of scope you noticed
  instead of fixing it.
