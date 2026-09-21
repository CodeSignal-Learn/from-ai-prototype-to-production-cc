# Telemetry: what the assistant records about each request

Every request produces a trace: one `request received` event, one event per step (`classify`,
`lookup`, `draft`, `checks`), and one final `request` event whose status is `ok`, `escalated`,
`flagged`, or `failed`. Events are JSON lines (`support_assistant/telemetry/events.py`), written
to the file named by `ASSISTANT_EVENTS_FILE` or the CLI's `--events`, and kept in memory when
neither is set. `python3 -m support_assistant.telemetry.metrics <log>` recomputes the
measurements below from a log; nothing in a report exists that is not in the events.

## What an event says, and what it never says

An event is an operational fact: which step, how long, which status, how many tokens, which
versions. It carries request ids, trace ids, categories, routes, reasons, article slugs, counts,
lengths, and hashes. It never carries the customer's text or the draft's text: the request body
appears as `{"chars": 102, "sha256": "728e9a17f077"}`, a draft the same way. A log can therefore
be kept for months, shipped to a dashboard, and read by anyone on the team without becoming a
second copy of customer messages. `test_events_carry_no_customer_or_draft_text` pins this.

An event also never says whether a draft was good. "The draft step took 2.3 s and used 340
tokens" is a measurement; "the draft was grounded" is a judgment that needs the article, the
request, and a reader, and lives in `evals/`. Keeping the two apart is what lets the operations
work that follows alert on events in real time while quality is measured on a schedule.

## A trace, success path

Request REQ-2005 from the trial set, replayed (`results/events/trial-with-outage.jsonl`,
durations are the replay client's, not the model's):

| Step | Status | Duration | Attributes |
| --- | --- | --- | --- |
| request | received | | channel, flags, body fingerprint |
| classify | ok | 0.1 ms | category `orders_shipping`, confidence 0.95, 1 call, 256 in / 55 out tokens |
| lookup | ok | 0.0 ms | article `order-tracking`, method `keyword` |
| draft | ok | 0.1 ms | draft fingerprint, 1 call, 349 in / 118 out tokens |
| checks | ok | 0.1 ms | problems `[]` |
| request | ok | 0.8 ms | route `draft`, reasons `[]`, drafted, 2 calls, 605 in / 173 out tokens, versions |

Every event carries the same `trace_id`, so a log with concurrent requests interleaved is read
per request by grouping on it. Token usage is attributed to the step that made the call through a
metered client wrapper, which stays correct under concurrency (`test_tokens_are_attributed_to_the_step_that_used_them`).

## A trace, failure path

The same log was produced with `ASSISTANT_REPLAY_FAILURES=timeout,timeout,timeout,rate_limit`:
the first request's three classification attempts time out and the fourth attempt, on the next
request, is rate-limited once and then served.

```text
classify  status unavailable  duration 35.6 ms  attempts 3  last_error LLMTimeout  category other
lookup    status ok           article null  method keyword
request   status escalated    route human_review  reasons [classification_unavailable, unknown_category, no_reference_article]  calls 0
```

The request completes: a person receives it with the reason that says which step was
unavailable, the trace records three attempts and the error type, and the batch continues. The
35.6 ms is the retry policy's backoff at a 0.01 s base delay; in production it is 0.5 s, 1 s.

## Measurements

`python3 -m support_assistant.telemetry.metrics results/events/batch-replay.jsonl --input-rate 1.00 --output-rate 5.00`
on the 40-request batch, replay client, concurrency 4:

| Measure | Value |
| --- | --- |
| Requests completed / failed | 40 / 0 |
| Requests with a model step unavailable | 0 |
| Latency p50 / p95 / max | 2.2 / 2.9 / 3.3 ms (replay; live is about 2.4 s per request) |
| Model calls, input tokens, output tokens | 75, 22,658, 6,293 |
| Estimated cost at $1.00 / $5.00 per million | $0.0541 total, $0.00135 per request |
| Routes | 33 draft, 7 human review; 35 drafts produced, 2 flagged |
| Reasons | hostile 1, legal 1, insufficient information 1, unknown category 3, no article 3, unverifiable promise 1, ungrounded number 1 |
| Versions | app 2.1.0, prompt 81ec9d26f2c2, variant v1, model claude-haiku-4-5, client replay |

The trial run with the injected outage: 25 requests, 1 with classification unavailable, 42
completed calls and 4 failed attempts (three timeouts, one rate limit), $0.0281, p95 13.5 ms and
max 36.2 ms, both from the retried requests. That is the shape an
outage has in this log: a small number of slow, escalated requests with `attempts` on their
classify event, not a failed batch.

## Cost is estimated from rates, never known

The provider's rates are inputs (`ASSISTANT_INPUT_RATE_PER_MILLION`,
`ASSISTANT_OUTPUT_RATE_PER_MILLION`, or the metrics flags), set together or not at all. Without
them the report says "not computed". Tokens are the provider's own counts as returned with each
completion, so the estimate is exact for the tokens and only as good as the rates.

## Limits
- Durations in a replay log are the replay client's. Live latency is measured live: the
  evaluation runs record wall time per case, and the held-out runs in `results/evals/` carry it.
- Retries are visible as `attempts` on a step event, not as separate events per attempt.
- Trace ids are random, so two replays of the same traffic agree in every field except
  `trace_id`; reports and alerts key on `request_id` for that reason.
- The events say which article was chosen and by which method; they do not say whether it was
  the right one. That is `article_correct` in the evaluation summaries.
- Nothing reads the events yet. Objectives, alerts, and drift reports over event windows are the
  next steps.
