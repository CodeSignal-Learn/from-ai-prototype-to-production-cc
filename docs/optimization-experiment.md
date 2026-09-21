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
| Acceptable under the rubric, weighted by requests | 42% | 71% |
| Missed escalation (drafted, label says a person) | 34% | 3% |
| Over-escalation | 2% | 11% |
| Unsupported statement (judged) | 13% | 12% |
| Wrong article on an answerable request, share of all requests (of the 195 answerable) | 12% (30%) | 6% (16%) |
| Drafts produced | 371 | 174 |
| Requests to a person | 146 (29%) | 344 (69%) |
| of which `article_does_not_answer` | 0 | 173 (35%) |
| Flagged drafts | 17 | 18 |
| Model calls | 871 | 847 |
| Input tokens | 256,236 | 513,434 |
| Output tokens | 64,032 | 58,611 |
| Estimated cost at $1.00 / $5.00 per million | $0.576, $0.00115 per request | $0.807, $0.00161 per request |
| Latency p50 / p95 (simulated) | 3.5 s / 4.3 s | 3.2 s / 4.4 s |
| Model steps unavailable | 0 | 0 |
| Probes acceptable (22) | 11, 6 missed escalations | 12, 1 missed escalation |
| Development split acceptable (112) | 52 | 74 |
| Suite regressions against the version's reference | 0 | 0 (the v2 reference is the candidate run on the same recordings) |
| Against v1's reference, regressions / recoveries | | development 12 / 34, probes 3 / 4 |

### Reading it
- **Quality**: the held-out prediction held on traffic. Acceptable share up by 29 points on the
  week, missed escalations down from a third of requests to 3%, wrong articles halved, the
  unsupported-statement rate unchanged. Over-escalation rose to 11% (53 of the 500 requests).
  Most of it (40) is the drafter declining an answerable request: a new phone whose codes are
  rejected (EV-3050, 9 requests), points missing after an account merge (EV-3059, 8), and
  smaller cases. Seven are a draft flagged as a promise (EV-3048), and six a Spanish shipping
  question that v2 classifies as `other` (EV-3095). The held-out cases the comparison named
  (account deletion, the 2 pm shipping rule) are not in this week's traffic. Against v1's
  reference runs, three probes v1 answered acceptably fail under v2: ADV-4005 and ADV-4022 are
  over-escalated, and ADV-4004, classified as billing, no longer states that refunds go to the
  original payment method.
- **Cost**: input tokens doubled: every classification now carries the article list (about 400
  tokens, four fifths of the increase), and the v2 drafting prompt is longer. Output tokens
  fell because fewer drafts are written. Net +40% per request, at $0.0016 against a
  gate of $0.01. The spend objective is not at risk.
- **Latency**: the median fell by 0.3 s (a declined draft is a short answer) and the p95 rose by
  0.1 s, far inside the 8 s objective.
- **Reliability**: no difference; the same retry policy, the same fallbacks, the same zero
  unavailable steps on a clean week.
- **Workload**: this is the real change. Agents receive 197 fewer drafts and 198 more
  escalations (208 requests newly escalated, 10 no longer), and 173 requests carry
  `article_does_not_answer`. Under v1, 164 of those 173 had a draft, 137 of them saying "a
  specialist will follow up", which an agent would open and read; for the 124 a person should
  answer, the agent would then discard it. The other 40 are answerable by label and are the
  over-escalation above. In routing counts, the work moved from the review queue to the
  escalation queue and got a label. These counts are a proxy for workload: agents worked
  neither queue in the replay, so whether a labeled escalation takes less of their time than a
  deferral they read and discard is a hypothesis for the first live week.
  The escalation-share objective, written for v1's behavior, would be missed every day under v2
  (0.69 against 0.45), so it was re-baselined to 0.80, above the replayed week's highest day
  (0.76), with its reason recorded, and the alert threshold to 0.85. An objective describes the
  behavior the team adopted.

### Decision: adopted
`ASSISTANT_PROMPT_VARIANT` defaults to `v2` from app version 3.0.0. `v1` remains one setting
away and is the rollback named in the runbook. The suites' reference runs for v2 are the
candidate runs recorded before the rollout, and the scheduled evaluation compares against them.
One condition from the comparison report carried over: the R3 flags are still read by a person.
One was not met: the comparison asked for the action list in the drafting prompt, which still
names account deletion although the knowledge base covers it, to be fixed before the rollout.
Changing that wording is a new candidate with a new held-out set, and the 56 held-out cases are
spent, so the rollout went ahead on the measured prompt and the fix is deferred. Deferring it
accepts a known over-escalation: an account-deletion request reaches a person with
`article_does_not_answer` and no draft, as EV-3054 did in 3 of 3 held-out runs, where v1
drafted the procedure from the article. The replayed week holds no account-deletion request,
so it neither measured nor cleared this. The condition closes when a reworded prompt is
measured on the development split and the held-out set of dataset v2 and adopted; until then
it is a known limit in `docs/readiness-checklist.md`.

## 2. Skipping the draft call when the classifier names no article

### Hypothesis
Under v2 the classifier sees every article and returns `null` when none fits: 27 of 112
development cases, 16 of 56 held-out. About half of them (14, and 9 or 10) are classified
`other` and escalate without a draft call. For the rest, 13 development and 6 or 7 held-out,
the pipeline falls back to the keyword article and asks for a draft unless another rule
escalates, and the drafter almost always declines. Skipping that call would save a model call,
its tokens, and its latency on those requests (on week 2, 57 of 500, 37 of which would otherwise
have been drafted), with a quality risk on the cases where the fallback article would have
produced an acceptable draft: 3 development and 2 held-out cases were answerable by label.

### Method
A validated setting, `ASSISTANT_DRAFT_POLICY=skip_unnamed` (v2 only), that escalates with the
reason `no_article_named` instead of drafting. Stamped into every result's `versions`. Measured
with the same protocol as any candidate: development split, three held-out repeats against the
three v2 repeats (`results/evals/comparison/development-skip-unnamed.json`,
`held-out-skip-unnamed.json`), and the week-2 replay (`results/events/week-2-v2-skip.jsonl`).

### Results

| | v2, always draft | v2, skip when unnamed |
| --- | --- | --- |
| Development acceptable (112) | 74 | 74 (identical verdicts) |
| Held-out acceptable, mean of 3 (56) | 41.7 (40 to 44) | 42.0 (41 to 43) |
| Held-out missed / over-escalation, mean | 1.3 / 3.7 | 0.3 / 4.7 |
| Held-out cases improved / regressed | | 2 / 1 |
| Week-2 model calls | 847 | 810 (-4%) |
| Week-2 input tokens | 513,434 | 494,233 (-4%) |
| Week-2 cost per request | $0.00161 | $0.00157 (-2.5%) |
| Week-2 latency p50 / p95 | 3.2 s / 4.4 s | 3.1 s / 4.4 s |

### Reading it
The saving is real and small: 37 calls in 500 requests, 2.5% of cost, 80 ms at the median,
nothing at the tail. On the development split every verdict is identical, because the drafter
had already declined every one of those calls. On held-out, the policy moved the mean by a
third of a case and regressed one case: EV-3073, a shipping question to Alberta that the
classifier left unnamed and the keyword fallback answered acceptably from the shipping article
twice out of three, and that the policy escalates in all three. Two cases improved, EV-3117 by
one repeat and EV-3132 by two: both were deferrals the drafter wrote where a person should
answer, which the policy now hands over. That is within the run-to-run spread of the v2
prompts themselves.

### Decision: rejected
A saving of 2.5% does not buy one answerable request sent to a person on principle. The setting
stays in the code with its tests, default `always`, because the measurement was made and the
next person to have the idea should find the numbers, not repeat the experiment. If the
classifier's article choice improves to the point where `null` reliably means "no article
answers", the policy is worth measuring again; the signal to watch is how often the drafter
still answers an unnamed request acceptably: today one held-out case of the 7 the policy would
skip, EV-3073, in 2 of 3 repeats.

## What both experiments cannot show
Latency and cost come from a replay with simulated latency and real token counts; the live tail
and the live provider's variability are not in them. The rollout was a replay of one recorded
week, not a share of live traffic; agents did not work the v2 queue, so how they take to fewer
drafts and more labeled escalations is the question the first live week answers.
