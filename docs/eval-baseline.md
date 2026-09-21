# Baseline evaluation of the hardened assistant

Run `v1-development-baseline`: the 112 development cases of dataset v1 through the assistant at
v2 (`claude-haiku-4-5`, prompt version in the run summary), scored against rubric v1.1 with the
calibrated judge. Everything below is recomputed from `results/evals/v1-development-baseline/`
by `evals.runner`; the judged criteria carry the calibration caveats in
`docs/judge-calibration.md`.

## Headline

| | Count |
| --- | --- |
| Cases | 112 |
| Drafted | 88 |
| Acceptable under the rubric | 50 (0.45) |
| R1 routing pass | 73 |
| R2 missed escalation / over-escalation | 32 / 2 |
| R3 unsupported statement (judged) | 17 |
| R4 incomplete: fail / partial (judged) | 21 / 5 |
| R5 commitment or forbidden phrase | 11 |
| Correct article selected | 79 |

Half the failures come from two mechanisms, neither of which the POC trial could see.

## Finding 1: the assistant drafts when it should hand over

32 requests the label sends to a person received a draft. All 32 drafts defer ("a specialist
will follow up"); 20 are requests no article covers, 4 ask for an action on an order, 3 are
pre-sales questions, 2 carry a pasted card number. The model correctly notices that the article
does not answer and writes a deferral, and the pipeline queues that deferral as a draft. The
agent then reads a draft that says nothing, and the request is not in the escalation queue
where it belongs. Nothing in the pipeline distinguishes "the article answered" from "the model
declined to answer"; both are drafts.

This is the largest single cause of routing failures (R1 fail 39, of which 32 are this) and it
is invisible to the deterministic checks, because a deferral promises nothing.

## Finding 2: the wrong article is selected inside the right category

18 of 57 draft-expected cases were drafted from the wrong article. The keyword scorer in
`knowledge.py` picks the article with the most keyword hits; when no keyword hits, every article
scores zero and the first in alphabetical order wins: `account-merge` over `password-reset`,
`order-tracking` over `shipping-times`, `product-care` over `warranty-claims`,
`refund-timelines` over `returns-policy`. Every keywordless sign-in problem became an
account-merge draft; every warranty question without the word "warranty" became a product-care
draft. The model then, correctly, said the article did not answer and deferred, so the customer
got no answer the team has. These are most of the R4 fails (21) and most of the acceptable-rate
gap in `product_issue` and `returns_refunds`.

## Finding 3: unsupported statements are rarer than the POC review suggested, and of two shapes

17 drafts carry a statement the judge found unsupported; on the calibrated sample, about two in
three of the judge's fails hold up when read, so the true count is nearer 11 than 17. They are
extensions of a stated rule to a case it does not cover ("even after cancellation", EV-3023; a
summed delivery range, EV-3090), and deferrals that name an outcome ("get you the correct
fleece", "help you change your name", "we'll get this sorted"). None states a price or a policy
out of nothing. The drafting prompt's "use only facts stated in the article" holds for facts
and slips on inferences.

## Finding 4: the deterministic checks and labels catch what they were built for

- The five hostile and three legal cases, the two instruction cases, the oversized body, and
  seven of the eight too-short bodies went to a person on the rule meant for them. The eighth,
  EV-3162, "it doesn't work", clears the three-word minimum; it reached a person only because the
  model classified it `other`, not because anything noticed it was unanswerable.
- The two pasted card numbers were masked at intake and the drafts repeat nothing; but neither
  request reached a person. `sensitive_data_masked` is a flag with no routing consequence.
- Two over-escalations: one two-topic request classified `other`, and EV-3090, where the draft
  check `ungrounded_number` fired on a summed "3-6 business days". The check did its job.
- Eleven R5 fails: ten are forbidden phrases, and all ten are drafts that name the uncovered
  topic while deferring ("doesn't address sales tax", "shipping to Chile", "passkeys"), which
  the v1 phrase lists were too broad to allow; the eleventh is EV-3090. The lists were written
  more narrowly for the adversarial set; v1 is left as is and these ten are read as label noise,
  not draft failures.

## What this changes

- Findings 1 and 2 are the candidates for a revised prompt: let the model say that the article
  does not answer, and let it pick the article from the category's list, so the pipeline can
  route a non-answer to a person and ground the draft in the right article. That change is
  measured on the held-out split before anyone rolls it out.
- Finding 4 names two small deterministic gaps, masked sensitive fields and the three-word
  minimum, for the red-teaming unit to confirm and close.
- Finding 3 says the deterministic promise patterns should also cover deferrals that name an
  outcome, and that the judge remains the only detector for rule extensions.
