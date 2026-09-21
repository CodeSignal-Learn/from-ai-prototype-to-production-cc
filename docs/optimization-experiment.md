# Two changes, one adopted and one rejected

Both changes were measured the same way before anyone touched the default: quality on the
rubric (development and held-out cases, repeated runs), then cost, latency, reliability, and
workload on a replay of a recorded week under each version, then the evaluation and adversarial
suites again. The evidence for each is in `results/`, recomputed by the tools named; the
decisions are at the end of each section.

## 1. Rolling out the v2 prompts

### Hypothesis
The v2 prompt set (`docs/eval-comparison.md`: the classifier names the article, the drafter
declines when the article does not answer) turns drafted deferrals into escalations with a
reason and grounds more drafts in the right article, at the cost of more input tokens per
request and more requests in the escalation queue. The held-out comparison recommended release
through a controlled rollout; this is that rollout, on a replay of the recorded week 2 under
both versions.

### Method
`scripts/replay_traffic.py data/traffic/week-2.jsonl` twice, identical requests and arrival
times, `--variant v1` and `--variant v2`, on the replay client with simulated latency
(`results/events/week-2.jsonl`, `week-2-v2.jsonl`). Events compared with `ops/drift.py`
(`results/drift/week-2-v2-vs-v1.json`); quality on the week's cases weighted by request counts
with `ops/scheduled_eval.py --variant v2` (`results/evals/scheduled/2026-09-20-week-2-v2/`),
against the v1 run of the same week (`results/evals/scheduled/2026-09-20-week-2/`); the suites
under v2 against their v2 reference runs; the probes recorded under v2
(`results/evals/adv-v1-development-candidate/`).

### Results, 500 requests

| | v1 | v2 |
| --- | --- | --- |
| Acceptable under the rubric, weighted by requests | 57% | 75% |
| Missed escalation (drafted, label says a person) | 32% | 7% |
| Over-escalation | 0.4% | 9% |
| Unsupported statement (judged) | 8% | 5% |
| Wrong article on an answerable request, share of all requests (of the 195 answerable) | 9% (24%) | 2% (5%) |
| Drafts produced | 358 | 190 |
| Requests to a person | 146 (29%) | 318 (64%) |
| of which `article_does_not_answer` | 0 | 155 (31%) |
| Flagged drafts | 4 | 8 |
| Model calls | 858 | 845 |
| Input tokens | 338,751 | 699,407 |
| Output tokens | 91,237 | 72,425 |
| Estimated cost at $0.10 / $0.50 per million | $0.07949, $0.000159 per request | $0.10615, $0.000212 per request |
| Latency p50 / p95 (simulated) | 4.5 s / 5.7 s | 3.9 s / 5.7 s |
| Model steps unavailable | 0 | 0 |
| Probes acceptable (22) | 9, 6 missed escalations | 15, no missed escalation |
| Development split acceptable (112) | 64 | 83 |
| Suite regressions against the version's reference | 0 | 0 (the v2 reference is the candidate run on the same recordings) |
| Against v1's reference, regressions / recoveries | | development 14 / 33, probes 1 / 7 |

### Reading it
- **Quality**: the held-out prediction held on traffic. Acceptable share up by 18 points on the
  week (57% to 75%), missed escalations down from a third of requests to 7%, wrong articles from
  9% of requests to 2%, the unsupported-statement rate from 8% to 5%. Over-escalation rose to 9%
  (47 of the 500 requests). Most of it (41) is the drafter declining an answerable request: a
  new phone whose codes are rejected (EV-3050, 9 requests), a lost authenticator app (EV-3004,
  9), points missing after an account merge (EV-3059, 8), a Spanish shipping question (EV-3095,
  6), and smaller cases. Four are drafts flagged as a promise (EV-3109 and EV-3126), and two a
  low-confidence classification (EV-3119). The held-out cases the comparison named (account
  deletion, the 2 pm shipping rule, the 60-day window) are not in this week's traffic. Against
  v1's reference runs, one probe v1 answered acceptably fails under v2: ADV-4003, a Saturday
  delivery question, is declined with `article_does_not_answer`.
- **Cost**: input tokens doubled: every classification now carries the article list (about 570
  tokens, four fifths of the increase), and the v2 drafting prompt is longer. Output tokens
  fell because fewer drafts are written. Net +33% per request, at $0.0002 against a
  gate of $0.01. The spend objective is not at risk.
- **Latency**: the median fell by 0.6 s (a declined draft is a short answer) and the p95 did not
  move (5.7 s), far inside the 8 s objective.
- **Reliability**: no difference; the same retry policy, the same fallbacks, the same zero
  unavailable steps on a clean week.
- **Workload**: this is the real change. Agents receive 168 fewer drafts and 172 more
  escalations (174 requests newly escalated, 2 no longer), and 155 requests carry
  `article_does_not_answer`. Under v1, all 155 had a draft, 125 of them saying "a
  specialist will follow up", which an agent would open and read; for the 114 a person should
  answer, the agent would then discard it. The other 41 are answerable by label and are the
  over-escalation above. In routing counts, the work moved from the review queue to the
  escalation queue and got a label. These counts are a proxy for workload: agents worked
  neither queue in the replay, so whether a labeled escalation takes less of their time than a
  deferral they read and discard is a hypothesis for the first live week.
  The escalation-share objective, written for v1's behavior, would be missed every day under v2
  (0.64 against 0.45), so it was re-baselined to 0.80, above the replayed week's highest day
  (0.71), with its reason recorded, and the alert threshold to 0.85. An objective describes the
  behavior the team adopted.

### Decision: adopted
`ASSISTANT_PROMPT_VARIANT` defaults to `v2` from app version 3.0.0. `v1` remains one setting
away and is the rollback named in the runbook. The suites' reference runs for v2 are the
candidate runs recorded before the rollout, and the scheduled evaluation compares against them.
One condition from the comparison report carried over: the R3 flags are still read by a person.
One was not met: the comparison asked that v2 stop declining the requests v1 answers before the
rollout. v2's action list no longer names account deletion, yet three held-out cases are declined
in 3 of 3 runs that v1 answered acceptably in 3 of 3: EV-3054, a deletion request worded as an
action; EV-3083, whose 2 pm cut-off is in another article than the one its topic picks; and
EV-3102, a 60-day window read against the customer's dates. Changing the prompt for them is a
new candidate with a new held-out set. The 56 held-out cases are spent for it: the three were
found by reading held-out cases, and a rewording would be scored on the cases it was written
for. The draft policy below was designed from development cases and measured on the held-out
set as a second experiment, without tuning on it. So the rollout went ahead on the measured
prompt and the fix is deferred. Deferring it accepts known over-escalations: requests like these
reach a person with `article_does_not_answer` and no draft, where v1 drafted the answer from
the article. The replayed week holds none of the three, so it neither measured nor cleared
them; its 41 declines of answerable requests (above) are the same kind of cost on traffic. The
condition closes when a reworded prompt is measured on the development split and the held-out
set of dataset v2 and adopted; until then it is a known limit in `docs/readiness-checklist.md`.

## 2. Skipping the draft call when the classifier names no article

### Hypothesis
Under v2 the classifier sees every article and returns `null` when none fits: 20 of 112
development cases, 11 or 12 of 56 held-out. Most of them (14, and 8 or 9) are classified
`other` and escalate without a draft call. For the rest, 6 development and 2 to 4 held-out,
the pipeline falls back to the keyword article and asks for a draft unless another rule
escalates, and the drafter almost always declines. Skipping that call would save a model call,
its tokens, and its latency on those requests (on week 2, 30 of 500, 26 of which would otherwise
have been drafted), with a quality risk on the cases where the fallback article would have
produced an acceptable draft: none of those development or held-out cases is answerable by label.

### Method
A validated setting, `ASSISTANT_DRAFT_POLICY=skip_unnamed` (v2 only), that escalates with the
reason `no_article_named` instead of drafting. Stamped into every result's `versions`. Measured
with the same protocol as any candidate: development split, three held-out repeats against the
three v2 repeats (`results/evals/comparison/development-skip-unnamed.json`,
`held-out-skip-unnamed.json`), and the week-2 replay (`results/events/week-2-v2-skip.jsonl`).

### Results

| | v2, always draft | v2, skip when unnamed |
| --- | --- | --- |
| Development acceptable (112) | 83 | 83 (identical verdicts) |
| Held-out acceptable, mean of 3 (56) | 43.3 (43 to 44) | 43.3 (43 to 44) (identical verdicts) |
| Held-out missed / over-escalation, mean | 2.7 / 5.0 | 2.7 / 5.0 |
| Held-out cases improved / regressed | | 0 / 0 |
| Week-2 model calls | 845 | 819 (-3.1%) |
| Week-2 input tokens | 699,407 | 681,592 (-2.5%) |
| Week-2 cost per request | $0.000212 | $0.000208 (-1.8%) |
| Week-2 latency p50 / p95 | 3.9 s / 5.7 s | 3.8 s / 5.7 s |

### Reading it
The saving is real and small: 26 calls in 500 requests, 1.8% of cost, 24 ms at the median,
nothing at the tail. It changed no verdict: on the development split and on each held-out
repeat, every case has the same route and verdicts with the policy as without it. The policy
fired on 6 development cases and on 2 to 4 held-out cases per repeat, all of them requests a
person should answer, and each reached a person either way: the drafter declined every call the
policy skipped, and the cases that never reached the drafter were escalated by another rule as
well.

### Decision: rejected
The saving is 26 calls in 500 requests, 1.8% of the cost, and that is too small to justify the
policy. The measurement shows no loss: no verdict changed on development or held-out, and on the
replayed week every skipped call ended in a decline. It also could not show one, because none of
the cases the policy skipped there was answerable by label. Against the saving, the policy is
one more setting stamped into every result, one more escalation reason for agents and the
on-call to read, and a rule that turns every future `null` from the classifier into a hand-over
without asking the drafter. At a cost per request that is already a fiftieth of the gate, 1.8%
does not pay for that. The setting stays in the code with its tests, default `always`, so that
the next person to have the idea finds the numbers and does not repeat the experiment. If cost
per request becomes a constraint, the policy is worth measuring again on more cases; the signal
to watch is how often the drafter still answers an unnamed request acceptably: today, on none of
the development or held-out cases the policy would skip.

## What both experiments cannot show
Latency and cost come from a replay with simulated latency and real token counts; the live tail
and the live provider's variability are not in them. The rollout was a replay of one recorded
week, not a share of live traffic; agents did not work the v2 queue, so how they take to fewer
drafts and more labeled escalations is the question the first live week answers.
