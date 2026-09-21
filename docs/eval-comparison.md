# Baseline versus candidate: the v2 prompts

Decision this document supports: should the v2 prompt set replace v1 as the assistant's default?
Recommendation at the end. Numbers come from `results/evals/comparison/held-out.json`, produced
by `evals.report` from six runs; nothing here was computed by hand.

## What v2 changes

Two findings from `docs/eval-baseline.md` drove the candidate:

- **The classifier picks the article.** The v2 classification prompt lists every article with its
  topics and returns the slug that answers the request. The pipeline uses it only if the slug
  exists and belongs to the category; otherwise the keyword lookup runs as before. This targets
  finding 2, the alphabetical tie-break that sent every keywordless request to the first article in its
  category, the wrong one whenever the answer lives in another.
- **The drafter may decline.** The v2 drafting prompt answers `NO_ANSWER` when the article
  contains nothing that addresses the question, when the whole request is an action on an order
  or account, or when the answer needs a safety judgment. The pipeline turns that into an
  escalation with the reason `article_does_not_answer` and no draft. This targets finding 1, the
  drafted deferral that sat in the review queue instead of the escalation queue. The prompt also
  forbids extending a rule to an unmentioned situation and describing what a specialist can do.

The first wording of the drafting prompt declined far too often in a run that was not
kept, including requests the article answered outright ("two identical amounts of 74.50
left my account", "final sale, wrong size"). It was reworded to decide first whether the article contains a fact that answers
the question, even in part, and to decline only when it does not. Only the reworded version was
run on held-out cases, after clearing a bar written down before its development run was read:
more acceptable results than the after-repair run, fewer missed escalations, and
over-escalations rising by less than missed escalations fell. Development split, single run each (`results/evals/comparison/development.json`):
acceptable 64 to 83 of 112, missed escalations 26 to 5, over-escalations 1 to 11, correct
article 87 to 103.

## Protocol

Dataset v1, held-out split, 56 cases that were not read while writing either prompt. Three live
runs per side with `claude-haiku-5-5`, each repeat recorded under its own key so the spread
across repeats is the model's own variability. The same judge (prompt `4feda4d1cbbc`,
calibration in `docs/judge-calibration.md`) scored every draft. Baseline prompt `481f9fc0f782`
(v1), candidate `b65664d16794` (v2). The report refuses runs on different datasets, splits,
judges, or mixed prompt versions.

## Results

| Measure (of 56) | Baseline, mean (range over 3 runs) | Candidate, mean (range) | Change |
| --- | --- | --- | --- |
| Acceptable under the rubric | 38.7 (38 to 40) | 43.3 (43 to 44) | +4.7 |
| R1 routing pass | 43.0 (43 to 43) | 46.7 (46 to 47) | +3.7 |
| R2 missed escalation | 12.0 (12 to 12) | 2.7 (2 to 3) | -9.3 |
| R2 over-escalation | 0.0 (0 to 0) | 5.0 (5 to 5) | +5.0 |
| R3 unsupported statement (judged) | 1.3 (0 to 2) | 3.3 (3 to 4) | +2.0 |
| R4 fail (judged) | 4.3 (4 to 5) | 0.3 (0 to 1) | -4.0 |
| R4 partial (judged) | 4.7 (3 to 7) | 3.3 (3 to 4) | -1.3 |
| R5 commitment | 2.3 (2 to 3) | 0.0 (0 to 0) | -2.3 |
| Drafts produced | 38.0 (38 to 38) | 23.7 (23 to 24) | -14.3 |
| Correct article | 45.0 (45 to 45) | 49.0 (48 to 50) | +4.0 |

The acceptable ranges do not overlap: the worst candidate run (43) beats the best baseline run
(40) by three cases. The missed-escalation ranges do not overlap either, and that is the change
that matters most: the twelve held-out requests the baseline drafted a deferral for are the same
twelve in every run, and the candidate hands over nine to ten of them.

### By category, mean acceptable

| Category | Cases | Baseline | Candidate |
| --- | --- | --- | --- |
| billing | 8 | 4.3 | 6.3 |
| account_access | 8 | 4.0 | 5.0 |
| orders_shipping | 12 | 8.7 | 8.7 |
| returns_refunds | 10 | 6.0 | 6.7 |
| product_issue | 10 | 7.7 | 8.7 |
| other | 8 | 8.0 | 8.0 |

Every category improves or holds. `orders_shipping` holds because its four improved cases and
its four regressions cancel out; the regressions are below. By tag, the whole gain is on requests
a person must answer (not covered: 0 to 6.3 of 10; action required: 0 to 2 of 2), while the
untagged requests, ordinary questions the articles answer, go from 24.3 to 21.7 of 28.

### Paired, per case

14 cases improved, 9 regressed, 33 unchanged. 10 cases had a different outcome in at least one
of their three runs on one side or the other, which is the size of the noise a single run
carries: about a sixth of the cases can flip on a rerun, on either prompt.

The nine regressions, read one by one:

- **EV-3054, "Please delete my account and everything you have on me."** Baseline drafts the deletion procedure from the
  account article, acceptable in 3 of 3. Candidate declines in 3 of 3. Its action list no longer
  names deletion, but the rule still declines a whole request that is an action rather than a
  question, and this one is, although the article says how to request it.
- **EV-3083, "I ordered at 1 pm on a Tuesday. Does that go out the same day?"** Baseline reaches
  the tracking article by keyword and answers in 3 of 3. Candidate picks the shipping-times
  article, which has no cut-off rule, and declines in 3 of 3. The classifier's article choice is
  right by topic and wrong by content: the 2 pm rule lives in the tracking article.
- **EV-3102, a return at about 70 days.** Baseline states the 60-day window, says the item falls
  outside it, and leaves the options to a specialist, acceptable in 3 of 3. Candidate declines in
  3 of 3 with the right article in hand: the answer is the stated window read against the
  customer's dates, and the candidate does not treat that as an answer.
- **EV-3080, shipped two days ago with no tracking number.** The candidate guesses a reason in
  every run: the details "may still be on their way", or the order "may not have left yet, even
  though it shows as shipped". The article gives none and the case forbids inventing one; the
  baseline points back to the Orders page or defers. Judge R3 fail in 3 of 3, rightly.
- **EV-3035, a receipt for a manufacturer's warranty.** Both sides say the invoice "should work as
  proof of purchase", which the article does not say. The judge fails it in the two candidate
  drafts that tie it to the manufacturer's registration and passes it in all three baseline
  drafts.
- **EV-3093 and EV-3141.** Both sides answer the same way; the judge fails a plain deferral in
  the candidate's drafts ("A specialist will follow up with you on your order.", 2 of 3; "a
  specialist will follow up with you about your invoice request", 1 of 3).
- **EV-3097, refund timing.** The candidate says the refund "should fall within that
  five-business-day window", as all three baseline drafts do; judge fail in 1 of 3.
- **EV-3159, "order 49355" and nothing else.** Both sides send it to a person for missing
  information; the candidate classifies it `other` in 2 of 3 runs, so R1 fails on the category,
  and a person handles it either way.

Four of the nine are the candidate's own: three requests the baseline answered well and the
candidate declines (EV-3054, EV-3083, EV-3102), and a guessed reason (EV-3080). Four are the
judge reading the two sides differently (EV-3035, EV-3093, EV-3097, EV-3141), and one changes
nothing for the customer (EV-3159).

The read of the judge's R3 fails on both sides, required by the calibration policy, gives the
same picture. The judge flags more on the candidate, 3.3 against 1.3 a run, but most of the
difference is its own reading: plain deferrals (EV-3093, EV-3141) and sentences it passes in the
baseline's drafts (EV-3035, EV-3097, and EV-3122's two-year window, which both sides apply
alike). The baseline's flags are mostly the same kind ("check the Orders page to see if an
invoice exists", EV-3029; "any order" read to include a gift, EV-3039). What is real is about as
common on both sides: the proof-of-purchase sentence in all six EV-3035 drafts and the
candidate's guessed reason in EV-3080, against the baseline's deletion rule offered for a
stranger's sign-in (EV-3056) and a deferral that names an outcome the judge passed ("to help get
you a matching pair", EV-3104). The candidate did not remove unsupported conclusions; it traded
the baseline's for its own, in better-grounded drafts.

### What the change costs

- **About 14 fewer drafts per 56 requests.** Agents review fewer drafts and handle more
  escalations. On the held-out set, nine to ten of those escalations are requests where the
  baseline draft said nothing useful, so the review it saved was not worth having. Five are
  over-escalations of answerable requests, the same five in every run: EV-3054, EV-3062,
  EV-3083, EV-3102, and EV-3104, all declined as `article_does_not_answer`. The baseline answered
  EV-3054, EV-3083, and EV-3102 acceptably in all three runs; it never answered EV-3062 or
  EV-3104 acceptably, because it drafted both from the wrong article.
- **Longer classification prompts.** The article list and the longer v2 instructions add about 570
  input tokens (573) to every classification, and declined requests save only their output tokens. Replayed in full, the
  development run used 159,000 input tokens for 112 requests against 77,000 for the baseline,
  and 18,100 output tokens against 21,100: the candidate costs about twice the input. (The live
  run's own usage line reads lower, because completions served from existing recordings are not
  counted.)
- **A new failure to watch.** `article_does_not_answer` is a model decision. A model or prompt
  change that makes it fire more often looks like safety and is actually silence.

## Recommendation: release, through a controlled rollout, not now

Adopt v2 as the default prompt set, on these conditions:

1. **Roll it out under measurement, not by switching the default.** The operations work that
   follows this evaluation should run v2 on a share of traffic or on a replay of recorded traffic,
   with the escalation rate, the `article_does_not_answer` rate, and the drafted share as the
   numbers to watch, and v1 one configuration change away. Until then `ASSISTANT_PROMPT_VARIANT`
   stays `v1`.
2. **Stop declining the requests v1 answers before the rollout.** v2 declines EV-3054, EV-3083,
   and EV-3102 in every run, and v1 answers all three acceptably in every run: a request worded
   as an action whose answer is how to ask for it, an article chosen by topic that does not hold
   the rule, and a stated window read against the customer's dates. The fix changes the v2 prompt
   and so its prompt version: it is a new candidate, not the one measured here. It runs on the
   development split, then on the new held-out set of dataset v2, since these 56 cases are spent,
   and the rollout starts from that result.
3. **Keep reading R3 flags.** The candidate still states conclusions the article does not, at
   about the baseline's rate once the flags are read: a guessed reason for a missing tracking
   number, an invoice offered as a manufacturer's proof of purchase. The judge flags more than it
   finds there and passes some of them; a person confirms them; the drafting prompt's rule against
   inference is not sufficient on its own.
4. **Report the numbers as counts on 56 cases.** A move of 4.7 acceptable cases is larger than
   the spread seen across three runs on either side (2 and 1 cases), and that is the strength of
   the evidence: clear on the main effect, unable to separate a difference of a few cases from
   rerun variation, and silent on categories where the sample is eight requests. Three runs give
   observed ranges, not a confidence interval.

Hold would be the answer if what v2 stops answering weighed as much as what it starts handing
over. Three of its five over-escalations are requests the baseline answered well in every run,
and they are why condition 2 comes before the rollout; against them, v2 hands over nine to ten
of the twelve requests the baseline drafted for although a person must answer. A missed
escalation is a safety failure and an over-escalation a cost, so the trade favors v2 even before
condition 2. Reject would be the answer if the candidate invented more than the baseline; the
judge flags more, but read case by case it invents about the same, in better-grounded drafts.
Release, with the rollout carrying the risk that this comparison cannot measure: how agents work
with fewer drafts and more escalations.

## Limits

- 56 held-out cases, one reviewer's labels, one judge with slight agreement on R3, more lenient
  than the reviewer, and substantial on R4. Rates per category rest on 8 to 12 requests.
- Three held-out cases, EV-3029, EV-3039, and EV-3063, carry the label issues
  `docs/eval-dataset.md` lists for v2. They were read to document the dataset, not to tune
  either prompt. Without them the acceptable means are 36.3 and 40.3 of 53, and the ranges
  (36 to 37, 40 to 41) still do not overlap.
- Three repeats show a range of the model's run-to-run variability, not its limits, and say
  nothing about the labels; a second reviewer's labels would move some verdicts on both sides.
- The judge was calibrated on v1 drafts. The v2 drafts were not reviewed against it, which is
  why every judged R3 fail in the regressions was read.
- The held-out cases have now been read for this report. They are spent for tuning: the next
  candidate is measured on a new held-out set, and these 56 move to development in dataset v2.
- Agent workload and customer outcome are not measured here. The evaluation says the drafts and
  routes are better by the rubric; the rollout says whether the team is.
