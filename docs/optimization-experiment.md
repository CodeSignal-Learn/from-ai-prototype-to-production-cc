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
with `ops/scheduled_eval.py --variant v2` (`results/evals/scheduled/2026-09-20-week-2-v2/`);
the suites under v2 against their v2 reference runs; the probes recorded under v2
(`results/evals/adv-v1-development-candidate/`).

### Results, 500 requests

| | v1 | v2 |
| --- | --- | --- |
| Acceptable under the rubric, weighted by requests | 42% | 71% |
| Missed escalation (drafted, label says a person) | 34% | 3% |
| Over-escalation | 2% | 11% |
| Unsupported statement (judged) | 13% | 12% |
| Wrong article on an answerable request | 12% | 6% |
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
| Suite regressions against the version's reference | 0 | 0 |

### Reading it
- **Quality**: the held-out prediction held on traffic. Acceptable share up by 29 points on the
  week, missed escalations down from a third of requests to 3%, wrong articles halved, the
  unsupported-statement rate unchanged. Over-escalation rose to 11%, most of it the cases the
  comparison already named (account deletion, the 2 pm shipping rule in the other article).
- **Cost**: input tokens doubled because every classification now carries the article list;
  output tokens fell because fewer drafts are written. Net +40% per request, at $0.0016 against a
  gate of $0.01. The spend objective is not at risk.
- **Latency**: the median fell (a declined draft is a short answer) and the tail did not move.
- **Reliability**: no difference; the same retry policy, the same fallbacks, the same zero
  unavailable steps on a clean week.
- **Workload**: this is the real change. Agents receive 197 fewer drafts and 198 more
  escalations, 173 of them carrying `article_does_not_answer`. Under v1 those 173 were drafts
  that said "a specialist will follow up", which an agent had to open, read, and discard. The
  work moved from the review queue to the escalation queue and got a label; it did not grow.
  The escalation-share objective, written for v1's behavior, would be missed every day under v2
  (0.69 against 0.45), so it was re-baselined to 0.75 with its reason recorded, and the alert
  threshold to 0.85. An objective describes the behavior the team adopted.

### Decision: adopted
`ASSISTANT_PROMPT_VARIANT` defaults to `v2` from app version 3.0.0. `v1` remains one setting
away and is the rollback named in the runbook. The suites' reference runs for v2 are the
candidate runs recorded before the rollout, and the scheduled evaluation compares against them.
Two conditions from the comparison report carried over: the R3 flags are still read by a person,
and the action list in the drafting prompt still names account deletion, which the knowledge
base covers; changing that wording is a new candidate with a new held-out set, and the 56
held-out cases are spent. It stays on the list.

## 2. Skipping the draft call when the classifier names no article

### Hypothesis
Under v2 the classifier sees every article and returns `null` when none fits: 27 of 112
development cases, 16 of 56 held-out. The pipeline then falls back to the keyword article and
asks for a draft, and the drafter almost always declines. Skipping that call would save a model
call, its tokens, and its latency on about a quarter of requests, with a quality risk on the
cases where the fallback article would have produced an acceptable draft: 4 development and 2
held-out cases were answerable by label.

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
third of a case and regressed one case in all three repeats: EV-3073, a shipping question to
Alberta that the classifier left unnamed and the keyword fallback answered acceptably from the
shipping article twice out of three. Two cases improved by a repeat each, which is within the
run-to-run spread of the v2 prompts themselves.

### Decision: rejected
A saving of 2.5% does not buy one answerable request sent to a person on principle. The setting
stays in the code with its tests, default `always`, because the measurement was made and the
next person to have the idea should find the numbers, not repeat the experiment. If the
classifier's article choice improves to the point where `null` reliably means "no article
answers", the policy is worth measuring again; the signal to watch is the share of unnamed
cases the drafter still answers acceptably, which is 2 of 56 today.

## What both experiments cannot show
Latency and cost come from a replay with simulated latency and real token counts; the live tail
and the live provider's variability are not in them. The rollout was a replay of one recorded
week, not a share of live traffic; agents did not work the v2 queue, so how they take to fewer
drafts and more labeled escalations is the question the first live week answers.
