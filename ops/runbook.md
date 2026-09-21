# Runbook: the support-request assistant in production

What to do when an alert fires or a person reports a problem. Every step reads something the
system already records (events, `/health`, evaluation results) or changes one configuration
value; nothing here edits code under pressure. Rehearsed on recorded traffic in
`docs/incident-2026-09-15.md`.

## The one fact to keep in mind

Nothing this assistant does reaches a customer without a person sending it. A bad hour costs
agents time, never customers a wrong answer. That is why every containment below is a
configuration switch that keeps the queue moving, and why no step here is "stop the service".

## Where to look

| Question | Where |
| --- | --- |
| What is running right now | `GET /health`: mode, client, model, prompt variant and version, app version |
| What happened to one request | Its trace in the event log: filter on `request_id`; the final `request` event has route, reasons, versions, tokens; step events have durations, `failed_calls`, `last_error` |
| What is happening this hour | `python3 -m ops.alerts <events>` for the rules and their history; `python3 -m ops.slo <events>` for the objectives by day |
| Did the traffic change | `python3 -m ops.drift --baseline <last week> --recent <this week>` |
| Did the assistant change | `versions` on request events; the scheduled evaluation's suite comparison against the reference runs (zero regressions means the shipped version is the shipped version) |
| Is the draft quality down | `python3 -m ops.scheduled_eval --traffic <window>`; never from events alone |

## Containment switches

All are environment variables read by `support_assistant/config.py`; restart the service after a
change and confirm with `/health`.

| Switch | Effect | Use when |
| --- | --- | --- |
| `ASSISTANT_MODE=rules` | Keyword routing and template drafts; no model calls; identical to the POC control | The model is unavailable or slow for more than one window, or drafts are wrong in a way the checks do not catch |
| `ASSISTANT_PROMPT_VARIANT=v1` | Back to the shipped prompts after a candidate rollout | The candidate's escalation, decline, or flagged rates move beyond what its comparison predicted |
| `ASSISTANT_MODEL=<previous model id>` | Pin the model | The provider moved an alias and drafts changed shape (flagged rate up, prompt version unchanged) |
| `ASSISTANT_CONCURRENCY=1`, `ASSISTANT_TIMEOUT_SECONDS=30` | Fewer requests in flight, more patience per call | Rate limits or a slow provider, before falling back to rules |
| `ASSISTANT_MAX_RETRIES=0` | Fail fast to a person instead of waiting out three timeouts | A confirmed outage where retries only add a minute per request |

## Procedures

### A. `retries_rising` (warning)

Requests are completing on a retry. Nothing is broken yet; this is the hour before an outage.

1. Open the windows' step events: `failed_calls` and `last_error`. Rate limits: lower
   `ASSISTANT_CONCURRENCY`. Timeouts: the provider is slow; check its status page.
2. Confirm the rules-mode fallback is ready: the current settings file with `ASSISTANT_MODE=rules`
   staged, and the on-call knows the restart command.
3. Watch the next window. If `model_unavailable` fires, go to B and switch on its **first**
   window; the warning already paid for the second.

### B. `model_unavailable` (high)

A share of requests reached a person because the model step failed after every retry.

1. Read the affected traces (the alert lists them): `attempts`, `last_error`, step durations.
   Three timeouts at 20 s is a provider outage; three rate limits is our concurrency or their
   quota; a plain error is a deployment problem (key, model id) and is fixed, not waited out.
2. If the rate is still above threshold in the next window, or a warning preceded this alert:
   set `ASSISTANT_MODE=rules`, restart, confirm `/health` says `rules`. Agents keep receiving
   template drafts; the queue does not stop.
3. Recovery: every hour, replay the last hour's requests on the model with `--limit` in a
   separate process (or watch the provider's status). When two consecutive hours would have been
   clean, switch back to `ASSISTANT_MODE=model` and confirm the next window's unavailable rate is
   zero.
4. Write the timeline (below) and file the outage with the provider if it was theirs.

### C. `latency_p95` (medium)

1. Per-step p50 from the metrics: classify, draft, or both. Both means the provider; draft alone
   means longer outputs (check output tokens) or a prompt change (check the prompt version).
2. Retries in the same windows (`failed_calls`) add backoff; treat as A.
3. Lower `ASSISTANT_CONCURRENCY`; raise `ASSISTANT_TIMEOUT_SECONDS` only within the objective. If
   p95 stays above 8 s for two more windows, rules mode as in B.

### D. `flagged_drafts` (medium)

The checks are catching promises or invented numbers more often. The drafts changed shape.

1. Prompt version and model on the request events: did either change in the window?
2. If the model alias moved: pin `ASSISTANT_MODEL` to the previous id.
3. If the prompt changed: `ASSISTANT_PROMPT_VARIANT` back to the previous variant.
4. Confirm on the replay client: run the development split of the evaluation suite; the
   reference run says what the drafts looked like before.

### E. `escalation_share` (low) or a drift signal

Not an incident. Run the drift report and the scheduled evaluation on the window. If the suites
show zero regressions, the traffic changed: hand the knowledge base owners the
`top_failing_cases`. Roll nothing back.

### F. A person reports a wrong draft

1. Find the trace by request id; read the article chosen and the checks' `problems`.
2. Run the case through the judge with the rubric (`evals.runner` on a one-case dataset, or by
   hand against `evals/rubric.md`). If the draft is unsupported and the checks passed it, it is
   a rule-extension or capability claim: add the request as a case in the next dataset version
   and, if it recurs, a probe in the adversarial set.
3. Nothing to switch unless the reports cluster in one window with a version change; then D.

## After every incident

Write `docs/incident-<date>.md`: the timeline with the alert times and the times a person acted,
the evidence read at each step, the containment and the moment `/health` confirmed it, how
recovery was verified, the customer and agent impact in requests, and the follow-ups. Add the
window to the recorded traffic if it taught the alerts something.

## What this runbook does not cover

- Credentials, quotas, and billing with the provider: the platform team's runbook.
- Changes to knowledge articles: the support team's process.
- Anything that sends a message: there is nothing that does.
