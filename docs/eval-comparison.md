# Baseline versus candidate: the v2 prompts

> Outcome: adopted on 2026-09-21 after the replayed rollout in `docs/optimization-experiment.md`;
> `v2` is the default from app version 3.0.0 and `v1` is the rollback.

Decision this document supports: should the v2 prompt set replace v1 as the assistant's default?
Recommendation at the end. Numbers come from `results/evals/comparison/held-out.json`, produced
by `evals.report` from six runs; nothing here was computed by hand.

## What v2 changes

Two findings from `docs/eval-baseline.md` drove the candidate:

- **The classifier picks the article.** The v2 classification prompt lists every article with its
  topics and returns the slug that answers the request. The pipeline uses it only if the slug
  exists and belongs to the category; otherwise the keyword lookup runs as before. This targets
  finding 2, the alphabetical tie-break that sent every keywordless request to the wrong article.
- **The drafter may decline.** The v2 drafting prompt answers `NO_ANSWER` when the article
  contains nothing that addresses the question, when the whole request is an action on an order
  or account, or when the answer needs a safety judgment. The pipeline turns that into an
  escalation with the reason `article_does_not_answer` and no draft. This targets finding 1, the
  drafted deferral that sat in the review queue instead of the escalation queue. The prompt also
  forbids extending a rule to an unmentioned situation and describing what a specialist can do.

The first wording of the drafting prompt declined on 61 of 112 development cases, including
requests the article answered outright ("two identical amounts left my account", "final sale,
wrong size"). It was reworded to decide first whether the article contains a fact that answers
the question, even in part, and to decline only when it does not. Only the reworded version was
run on held-out cases. Development split, single run each (`results/evals/comparison/development.json`):
acceptable 52 to 74 of 112, missed escalations 28 to 3, over-escalations 3 to 15, correct
article 79 to 96.

## Protocol

Dataset v1, held-out split, 56 cases that were not read while writing either prompt. Three live
runs per side with `claude-haiku-4-5`, each repeat recorded under its own key so the spread
across repeats is the model's own variability. The same judge (prompt `4feda4d1cbbc`,
calibration in `docs/judge-calibration.md`) scored every draft. Baseline prompt `81ec9d26f2c2`
(v1), candidate `559724143452` (v2). The report refuses runs on different datasets, splits,
judges, or mixed prompt versions.

## Results

| Measure (of 56) | Baseline, mean (range over 3 runs) | Candidate, mean (range) | Change |
| --- | --- | --- | --- |
| Acceptable under the rubric | 33.7 (32 to 35) | 41.7 (40 to 44) | +8.0 |
| R1 routing pass | 42.3 (41 to 43) | 48.7 (48 to 49) | +6.3 |
| R2 missed escalation | 12.0 (12 to 12) | 1.3 (0 to 3) | -10.7 |
| R2 over-escalation | 0.3 (0 to 1) | 3.7 (3 to 4) | +3.3 |
| R3 unsupported statement (judged) | 8.0 (6 to 10) | 6.7 (5 to 8) | -1.3 |
| R4 fail (judged) | 7.3 (7 to 8) | 2.0 (0 to 3) | -5.3 |
| R4 partial (judged) | 3.0 (3 to 3) | 4.3 (2 to 6) | +1.3 |
| R5 commitment | 2.3 (2 to 3) | 0.7 (0 to 1) | -1.7 |
| Drafts produced | 38.0 (38 to 38) | 24.0 (23 to 26) | -14.0 |
| Correct article | 44.7 (44 to 45) | 49.0 (49 to 49) | +4.3 |

The acceptable ranges do not overlap: the worst candidate run (40) beats the best baseline run
(35) by five cases. The missed-escalation ranges do not overlap either, and that is the change
that matters most: the twelve held-out requests the baseline drafted a deferral for are the same
twelve in every run, and the candidate hands over ten to twelve of them.

### By category, mean acceptable

| Category | Cases | Baseline | Candidate |
| --- | --- | --- | --- |
| billing | 8 | 3.7 | 6.0 |
| account_access | 8 | 3.7 | 5.7 |
| orders_shipping | 12 | 6.3 | 9.3 |
| returns_refunds | 10 | 5.3 | 6.3 |
| product_issue | 10 | 6.7 | 6.3 |
| other | 8 | 8.0 | 8.0 |

Every category improves or holds except `product_issue`, which loses a third of a case on
average; the reason is in the regressions below.

### Paired, per case

19 cases improved, 7 regressed, 30 unchanged. 19 cases had a different outcome in at least one
of their three runs on one side or the other, which is the size of the noise a single run
carries: about a third of the cases can flip on a rerun, on either prompt.

The seven regressions, read one by one:

- **EV-3054, "Please delete my account."** Baseline drafts the deletion procedure from the
  account article, acceptable in 3 of 3. Candidate declines in 3 of 3: its action list names
  account deletion, and the article does describe how to request it. The prompt's action list is
  wrong for this case.
- **EV-3083, "I ordered at 1 pm on a Tuesday, does it go out today?"** Baseline reaches the
  tracking article by keyword and answers. Candidate picks the shipping-times article, which has
  no cut-off rule, and then either declines or says the article does not specify. The
  classifier's article choice is right by topic and wrong by content: the 2 pm rule lives in the
  tracking article.
- **EV-3134, a harness failure with an injury and a lawyer.** Both sides escalate on the legal
  threat. The candidate classifies it `other`, the baseline `product_issue`; R1 fails on the
  category, the route is the same, and a person handles it either way.
- **EV-3129, boot sole separating after 14 months.** Both sides draft. The candidate uses the
  right article and then decides the claim: "sole separation from normal wear may not be covered".
  That is the coverage judgment the prompt forbids, and the judge is right to fail it. The
  baseline used the wrong article and deferred, which the rubric also fails.
- **EV-3102 and EV-3122, a return at 70 days and a seam at three years.** The candidate states
  the window and says the item is outside it, in 1 of 3 and 1 of 3 runs. Arithmetic on the
  article's own number; the judge fails it as a conclusion, a reviewer may pass it.
- **EV-3124, a jacket that wets out.** Right article, right instruction, plus "this is normal with
  use", which the article states as "coatings wear down with use". Judge fail in 1 of 3; a
  reviewer would likely pass it.

The read of the judge's R3 fails, required by the calibration policy, gives the same picture as
the development split: about half are plain deferrals or restatements the judge over-reads
("a specialist will follow up to investigate further", the tracking steps quoted verbatim), and
the other half are real: coverage judgments (EV-3129), reassurance stated as fact ("you're
likely within that window", EV-3112), and one invented mechanism ("your new items will begin
shipping once your return is picked up", EV-3114). The candidate did not remove the
rule-extension failure; it moved it from wrong-article drafts to right-article drafts.

### What the change costs

- **14 fewer drafts per 56 requests.** Agents review fewer drafts and handle more escalations.
  On the held-out set, ten to twelve of those escalations are requests where the baseline draft
  said nothing useful, so the review it saved was not worth having. Three to four are
  over-escalations of answerable requests (EV-3054, EV-3062, EV-3083, EV-3104 in most runs) that
  the baseline answered acceptably in two cases and unacceptably in two.
- **Longer classification prompts.** The article list adds about 500 input tokens per request;
  the declined drafts save their output tokens. On the development run the candidate used
  43,000 input tokens for 112 requests against 59,000 for the baseline, because it drafted less.
- **A new failure to watch.** `article_does_not_answer` is a model decision. A model or prompt
  change that makes it fire more often looks like safety and is actually silence.

## Recommendation: release, through a controlled rollout, not now

Adopt v2 as the default prompt set, on these conditions:

1. **Roll it out under measurement, not by switching the default.** The operations work that
   follows this evaluation should run v2 on a share of traffic or on a replay of recorded traffic,
   with the escalation rate, the `article_does_not_answer` rate, and the drafted share as the
   numbers to watch, and v1 one configuration change away. Until then `ASSISTANT_PROMPT_VARIANT`
   stays `v1`.
2. **Fix the action list before the rollout.** Remove "delete an account" from the decline list,
   since the knowledge base covers it, and re-run the development split. This is a wording change
   to v2, not a new candidate, and it needs no new held-out run unless it changes anything else.
3. **Keep reading R3 flags.** The candidate still produces coverage judgments and reassurances the
   article does not state, at about the baseline's rate. The judge finds them; a person confirms
   them; the drafting prompt's rule against inference is not sufficient on its own.
4. **Report the numbers as counts on 56 cases.** A move of 8 acceptable cases is beyond the
   run-to-run spread of 3 to 4, and that is the strength of the evidence: clear on the main
   effect, silent on anything smaller than three cases, and silent on categories where the sample
   is eight requests.

Hold would be the answer if the over-escalations were the same requests the baseline answered
well; they are not, in the main. Reject would be the answer if the candidate invented more than
the baseline; it invents about the same, in better-grounded drafts. Release, with the rollout
carrying the risk that this comparison cannot measure: how agents work with fewer drafts and
more escalations.

## Limits

- 56 held-out cases, one reviewer's labels, one judge with moderate agreement on R3 and
  substantial on R4. Rates per category rest on 8 to 12 requests.
- Three repeats bound the model's variability, not the labels'. A second reviewer's labels
  would move some verdicts on both sides equally.
- The held-out cases have now been read for this report. They are spent for tuning: the next
  candidate is measured on a new held-out set, and these 56 move to development in dataset v2.
- Agent workload and customer outcome are not measured here. The evaluation says the drafts and
  routes are better by the rubric; the rollout says whether the team is.
