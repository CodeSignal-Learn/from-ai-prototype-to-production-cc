# Drift report: week 2 against week 1

Two recorded weeks of traffic, 500 requests each, replayed on the same version of the assistant
(`data/traffic/week-1.jsonl` and `week-2.jsonl`, event logs in `results/events/`). Week 1 is the
baseline. `ops/drift.py` compares the event logs; `ops/scheduled_eval.py` measures quality on the
cases behind each week. The two answer different questions and are read together.

## What the events say (`results/drift/week-2-vs-week-1.json`)

Versions did not change between the weeks, so every difference is in what came in or in how the
same system handled it.

| Category | Week 1 | Week 2 | Change |
| --- | --- | --- | --- |
| account_access | 14.8% | 25.6% | +10.8 |
| orders_shipping | 27.8% | 17.2% | -10.6 |
| other | 4.4% | 12.8% | +8.4 |
| returns_refunds | 20.0% | 12.6% | -7.4 |
| billing | 19.6% | 15.2% | -4.4 |
| product_issue | 13.4% | 16.6% | +3.2 |

| Rate | Week 1 | Week 2 |
| --- | --- | --- |
| Escalation | 20.6% | 29.2% |
| Drafted | 84.4% | 74.2% |
| Flagged drafts | 5.0% | 3.4% |
| Model step unavailable | 0.0% | 0.0% |
| Latency p95 | 4,428 ms | 4,282 ms |
| Input tokens per request | 546 | 512 |

Reasons above the five-point threshold: `unknown_category` and `no_reference_article`, 4.4% to
12.8% each, the pair that marks a request classified `other`. The others moved by two points or
less: `ungrounded_number` 2.0% to 0.0%, `insufficient_information` +1.4, legal +1.0, hostile and
instruction +0.6.

Eight signals, all of kind **input shift**: four category shares, the escalation and drafted
rates, and the two reasons. Each carries what it does not prove. A higher escalation rate with a
higher share of `other` and account-access requests is what the same assistant does with a
different week, not evidence that it got worse; the report's next step is to measure quality on
the week's cases before anyone touches a version.

## What the evaluation says (`results/evals/scheduled/`)

The recurring evaluation ran as of 2026-09-13 for week 1 and 2026-09-20 for week 2, on the
replay client:

1. **The suites did not move.** The development split (52 of 112 acceptable) and the adversarial
   probes (11 of 22) reproduce their reference runs case for case: zero regressions, zero
   recoveries, zero changed verdicts, on both dates. The code, prompts, and checks are the ones
   that shipped. Nothing was written to `new-failures.jsonl`.
2. **The week's cases, weighted by how often each was asked:**

| Weighted by requests | Week 1 (500) | Week 2 (500) |
| --- | --- | --- |
| Acceptable under the rubric | 49% | 42% |
| Missed escalation (drafted, label says a person) | 18% | 34% |
| Over-escalation | 5% | 2% |
| Unsupported statement (judged) | 16% | 13% |
| Wrong article (answerable request, share of all requests) | 20% | 12% |

Among answerable requests the wrong-article rate is 30% in both weeks (99 of 333, 58 of 195); it
falls only because week 2 had fewer answerable requests.

The most frequent failing cases in week 2 are requests the knowledge base does not cover.
Three were drafted as deferrals where the label says a person should answer: EV-3066
(passkeys, 17 requests), EV-3151 (a website bug report, 11), and EV-3057 (adding a partner to
an account, 9, with a claim that an account cannot be shared). EV-3106 (a gift return without
an order number, 11) was escalated by the promise check, but its draft explains the ordinary
return process, which the case says not to do. The fifth, EV-3068 (a password reset with an
order question, 9), is the opposite failure: an answerable request escalated as `other`. In
week 1 the most frequent failures were EV-3090 (a summed delivery estimate the checks caught)
and EV-3095 (the Spanish shipping question).

## Reading the two together

The assistant's per-case results are unchanged; what changed is that week 2 asked it more
questions it cannot answer, and the shipped version's response to an unanswerable question is a
drafted deferral, which the rubric counts as a missed escalation. So:

- **Not a rollback.** There is no version to roll back to: the version stamps did not change,
  and the suites reproduce their reference runs case for case.
- **Two things to do instead.** First, the knowledge base owners get the list of what customers
  asked that no article answers: passkeys and third-party sign-in, website problems, shared
  accounts, gift returns, pre-sales stock questions. Those are articles or a routing rule, not
  prompts. Second, the pending candidate prompt set (`docs/eval-comparison.md`) turns exactly
  this failure into an escalation with a reason, and week 2 is the kind of week that makes its
  rollout worth scheduling.
- **Regression coverage.** The week's failing cases are already in the development set, so the
  suites cover them. The weighted numbers count only requests whose `source_case` names a
  dataset case: a request without one carries no weight and never appears in
  `top_failing_cases`, so a new kind of request is labeled and added to the next dataset version
  before the schedule can score it.

## How this runs on a schedule

`python3 -m ops.scheduled_eval --as-of <date> --traffic data/traffic/<week>.jsonl --label <label>`
once a week, after the week's traffic is recorded, and once after any version change. It runs
on the replay client, so it costs nothing and is deterministic; the traffic window is scored on the
dataset cases its requests were sampled from, which the development suite has already recorded. A live
window carries no `source_case`: its requests are sampled, stripped of customer details, labeled, and
added to a new dataset version before they can be scored. Each run writes
its summary next to the previous ones and prints the previous window's numbers beside the new
ones, so a drift in quality is visible as a trend and not only as a threshold.

## Limits
- Two weeks, one shift, chosen to be visible. A real drift is smaller and slower; the report's
  five-point thresholds are a starting point, not a calibration.
- The weighted quality numbers inherit the judge's calibration: R3 is a flag a person confirms,
  and rates lean pessimistic.
- The event-level signals cannot see a change in language, tone, or length that the categories
  do not capture; body length is profiled but not yet used as a signal.
- The suites and the traffic scoring run on the replay client, which serves the answers
  recorded for this model name and prompt. They show that the code, prompts, and checks are
  unchanged; whether the provider's model behind `claude-haiku-4-5` still answers the same way
  takes a live run of the suites.
