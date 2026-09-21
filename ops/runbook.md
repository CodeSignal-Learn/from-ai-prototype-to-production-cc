# Runbook: the support-request assistant in production

What to do when an alert fires or a person reports a problem. Every step reads something the
system already records (events, `/health`, evaluation results) or changes one configuration
value; nothing here edits code under pressure. Rehearsed on recorded traffic in
`docs/incident-2026-09-15.md`.

## The one fact to keep in mind

Nothing this assistant does reaches a customer without a person sending it. A bad hour costs
agents time and slows replies, and a wrong draft reaches a customer only if the person sending
it misses the mistake. That is why every containment below is a configuration switch that keeps
the queue moving, and why no step here is "stop the service".

## Where to look

| Question | Where |
| --- | --- |
| What is running right now | `GET /health`: mode, client, model, prompt variant and version, app version |
| What happened to one request | Its trace in the event log: filter on `request_id`; the final `request` event has route, reasons, versions, tokens; step events have durations, `failed_calls`, `last_error` |
| What is happening this hour | `python3 -m ops.alerts <events>` for the rules and their history; `python3 -m ops.slo <events>` for the objectives by day |
| Did the traffic change | `python3 -m ops.drift --baseline <last week> --recent <this week>` |
| Did the assistant change | `versions` on request events; the scheduled evaluation's suite comparison against the reference runs (zero regressions means the code and prompts are the shipped ones; on the replay client it cannot show a change in the provider's model behind the same name) |
| Is the draft quality down | `python3 -m ops.scheduled_eval --as-of <date> --traffic <window> --label <label>`; never from events alone |

## Containment switches

All are environment variables read by `support_assistant/config.py`; restart the service after a
change and confirm with `/health`.

| Switch | Effect | Use when |
| --- | --- | --- |
| `ASSISTANT_MODE=rules` | Keyword routing and template drafts; no model calls; identical to the POC control | The model is unavailable or slow for more than one window, or drafts are wrong in a way the checks do not catch |
| `ASSISTANT_PROMPT_VARIANT=v1` | Back to the previous prompts (the rollback after the v2 rollout) | v2's escalation, decline, or flagged rates move beyond what its comparison and the replayed rollout predicted |
| `ASSISTANT_MODEL=<previous model id>` | Pin the model | The provider moved an alias and drafts changed shape (flagged rate up, prompt version unchanged) |
| `ASSISTANT_CONCURRENCY=1`, `ASSISTANT_TIMEOUT_SECONDS=30` | One request in flight for batch runs (`/batches`, the CLI; single requests are not bounded by it, and 1 is the default), more patience per call | Rate limits during batch work, or a slow provider, before falling back to rules |
| `ASSISTANT_MAX_RETRIES=0` | Fail fast to a person instead of waiting out three timeouts | A confirmed outage where retries only add a minute per request |

## Procedures

### A. `retries_rising` (warning)

Requests are completing on a retry. Nothing is broken yet, and an outage may follow.

1. Open the windows' step events: `failed_calls` and `last_error`. Rate limits: pause batch runs
   or lower their `ASSISTANT_CONCURRENCY`. Timeouts: the provider is slow; check its status page.
2. Confirm the rules-mode fallback is ready: the current settings file with `ASSISTANT_MODE=rules`
   staged, and the on-call knows the restart command.
3. Watch the next window. If `model_unavailable` fires, go to B and switch on its **first**
   window; the warning already paid for the second.

### B. `model_unavailable` (high)

A share of requests reached a person because the model step failed after every retry.

1. Read the affected traces (the alert lists them): `attempts`, `last_error`, step durations.
   Three timeouts at 20 s point at a provider outage, three rate limits at our concurrency or
   their quota, and a plain error at a deployment problem (key, model id), which is fixed, not
   waited out. Check the shape against the provider's status page and the versions on the
   request events before deciding; timeouts on our own network look the same in a trace.
2. If the rate is still above threshold in the next window, or a warning preceded this alert:
   set `ASSISTANT_MODE=rules`, restart, confirm `/health` says `rules`. Agents keep receiving
   template drafts; the queue does not stop.
3. Recovery: watch the provider's status, and from a separate process send five of the last
   hour's requests, the rule's minimum, to the provider (`python3 -m support_assistant.cli
   <requests> --mode model --client live`; `scripts/replay_traffic.py` serves recorded answers
   and cannot probe it). When all five complete with no unavailable step, switch back to
   `ASSISTANT_MODE=model`. The next window on the model must be clean; if it is not, return to
   rules mode and probe again after the next window.
4. Write the timeline (below) and file the outage with the provider if it was theirs.

### C. `latency_p95` (medium)

1. Per-step p50 from the metrics: classify, draft, or both. Both points first at the provider or
   the network to it; draft alone at longer outputs (check output tokens) or a prompt change
   (check the prompt version).
2. Retries in the same windows (`failed_calls`) add backoff; treat as A.
3. Pause batch runs or lower their `ASSISTANT_CONCURRENCY`; raise `ASSISTANT_TIMEOUT_SECONDS` only
   within the objective. If p95 stays above 8 s for two more windows, rules mode as in B.

### D. `flagged_drafts` (medium)

The checks are catching promises or invented numbers more often. The drafts changed shape.

1. Prompt version and model on the request events: did either change in the window?
2. If the model alias moved: pin `ASSISTANT_MODEL` to the previous id.
3. If the prompt changed: `ASSISTANT_PROMPT_VARIANT` back to the previous variant.
4. Confirm on the replay client: run the development split of the evaluation suite; the
   reference run says what the drafts looked like before.

### E. `escalation_share` (low) or a drift signal

Not an incident. Run the drift report and the scheduled evaluation on the window. If the suites
show zero regressions and the drift signals are input shifts, the traffic changed: hand the
knowledge base owners the `top_failing_cases`. Roll nothing back.

### F. A person reports a wrong draft

1. Find the trace by request id; read the article chosen and the checks' `problems`.
2. Run the case through the judge with the rubric (`evals.runner` on a one-case dataset, or by
   hand against `evals/rubric.md`). If the draft is unsupported and the checks passed it, it is
   a rule-extension or capability claim: add the request as a case in the next dataset version
   and, if it recurs, a probe in the adversarial set.
3. If the reports cluster in one window with a version change, go to D. If unsupported drafts
   recur without one (a model alias can move under the same name), switch to rules mode, the
   switch for drafts wrong in a way the checks do not catch, while the cases are investigated.

### G. `spend` (low)

The estimated cost per request crossed $0.01 over a day. Not an incident.

1. Tokens per step and the running variant: `python3 -m support_assistant.telemetry.metrics
   <events> --input-rate <rate> --output-rate <rate>`, and `versions` on the request events.
2. The product owner decides whether the spend is the new normal or a regression to fix.
   Nothing to switch.

## After every incident

Write `docs/incident-<date>.md`: the timeline with the alert times and the times a person acted,
the evidence read at each step, the containment and the moment `/health` confirmed it, how
recovery was verified, the customer and agent impact in requests, and the follow-ups. Add the
window to the recorded traffic if it taught the alerts something.

## What this runbook does not cover

- Credentials, quotas, and billing with the provider: the platform team's runbook.
- Changes to knowledge articles: the support team's process.
- Anything that sends a message: there is nothing that does.
