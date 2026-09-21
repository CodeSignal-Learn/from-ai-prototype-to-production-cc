# Baseline evaluation of the hardened assistant

Run `v1-development-baseline`: the 112 development cases of dataset v1 through the assistant at
v2 (`claude-haiku-5-5`, prompt version in the run summary), scored against rubric v1.1 with the
calibrated judge. Everything below is recomputed from `results/evals/v1-development-baseline/`
by `evals.runner`; the judged criteria carry the calibration caveats in
`docs/judge-calibration.md`.

## Headline

| | Count |
| --- | --- |
| Cases | 112 |
| Drafted | 85 |
| Acceptable under the rubric | 62 (0.55) |
| R1 routing pass | 81 |
| R2 missed escalation / over-escalation | 28 / 1 |
| R3 unsupported statement (judged) | 9 |
| R4 incomplete: fail / partial (judged) | 14 / 10 |
| R5 commitment or forbidden phrase | 13 |
| Expected article selected (12 of them: none expected, none selected) | 87 |
| Correct article, draft-expected cases | 41 of 57 |

Thirty-nine of the 50 unacceptable results come from two mechanisms: 28 drafted deferrals and 11
of the 13 alphabetical tie-breaks. The POC trial showed both on a handful of requests (REQ-2024's
drafted deferral; six wrong-article deferrals) but was too small to count them.

## Finding 1: the assistant drafts when it should hand over

28 requests the label sends to a person received a draft. All 28 drafts defer ("a specialist
will follow up"); 21 are requests no article covers (20 labeled not covered, and a gift card
balance the labels put in `other`), 4 ask for an action on an order, 1 is a pre-sales question,
2 carry a pasted card number. In most of them the
model notices that the article does not answer and writes a deferral, and the pipeline queues
that deferral as a draft; the two card-number requests are answered from the article and still
needed a person. The
agent then reads a draft that says nothing, and the request is not in the escalation queue
where it belongs. Nothing in the pipeline distinguishes "the article answered" from "the model
declined to answer"; both are drafts.

This is the largest single cause of routing failures (R1 fail 31, of which 28 are this) and it
is invisible to the deterministic checks, because a deferral promises nothing.

## Finding 2: the wrong article is selected inside the right category

16 of 57 draft-expected cases did not get the expected article, and 13 of them are one
mechanism. The keyword scorer in `knowledge.py` picks the article with the most keyword hits;
when no keyword hits, every article scores zero and the first in alphabetical order wins:
`account-merge` over `password-reset`, `order-tracking` over `shipping-times`, `product-care`
over `warranty-claims`, `refund-timelines` over `returns-policy`. Every keywordless sign-in
problem became an account-merge draft; every warranty question that used none of the warranty
article's keywords (a snapped pole, a lost tip, a broken strap holder) became a product-care
draft. The model then, correctly, said the article did not answer and deferred, so the customer
got no answer the team has. A fourteenth case, EV-3115, is the same tie-break in the wrong
category, and two (EV-3105, EV-3109) picked the other article on a keyword hit. The tie-break
drafts are 11 of the 14 R4 fails and half of the unacceptable results in `product_issue`; the
other two (EV-3079, EV-3095) are R4 `partial`.

## Finding 3: unsupported statements are uncommon, mostly stretched rules, and mostly missed by the judge

9 drafts carry a statement the judge found unsupported, and four of them hold up when read: two
stretch a stated rule to a case it does not cover ("a replacement ships once the carrier scans
your return package" for a different jacket, EV-3108; the merge offered to two people, EV-3057)
and two state a conclusion as fact ("since heat helps the treatment bond", EV-3010; "Tracking
that is still updating is a good sign the package is moving", EV-3092). The rest are the judge's
errors: advice (EV-3003, EV-3075), plain deferrals (EV-3042, EV-3106), the article restated
(EV-3030). On the calibrated sample it also missed four real fails in 39 passes, all stretches
(a summed delivery range, EV-3090; the settings page widened to "account details", EV-3069;
EV-3044; EV-3139), so the true count is nearer 12 than 9: about one draft in seven, more than the
POC review's none in twenty, which set two stretches aside. No draft in this run names an
outcome (a replacement, a corrected item, a change made); the closest, EV-3139's "a specialist
will follow up with where to ship it", adds a step the article does not have. The drafting
prompt's "use only facts stated in the article" holds for most facts and slips on inferences.

## Finding 4: the deterministic checks and labels catch what they were built for

- The five hostile and three legal cases, the two instruction cases, and seven of the eight
  too-short bodies went to a person on the rule meant for them (the one oversized body is in the
  held-out split and was not run). The eighth,
  EV-3162, "it doesn't work", clears the three-word minimum; it reached a person only because the
  model classified it `other`, at low confidence, not because a rule noticed it was unanswerable.
- The two pasted card numbers were masked at intake and the drafts repeat nothing; but neither
  request reached a person. `sensitive_data_masked` is a flag with no routing consequence.
- One over-escalation: EV-3046, a two-topic request (an invoice and a delivery date) classified
  `billing` below the confidence threshold. The draft check `ungrounded_number` fired once, on
  EV-3031's "$4.30", a difference the draft worked out from the request's two totals; the label
  wants a person there, so the check did its job.
- Thirteen R5 fails: twelve are forbidden phrases. Ten are drafts that name the uncovered topic
  while deferring ("doesn't explain how sales tax is calculated", "whether we ship to APO
  addresses", "whether passkeys or hardware security keys are supported"), and two (EV-3034,
  EV-3047) restate the article's "Real duplicate charges are refunded within five business days"
  against a list that forbids "refund". The v1 phrase lists were too broad to allow either; v1 is
  left as is and these twelve are read as label noise, not draft failures. The thirteenth is
  EV-3031.

## What this changes

- Findings 1 and 2 are the candidates for a revised prompt: let the model say that the article
  does not answer, and let it pick the article from the category's list, so the pipeline can
  route a non-answer to a person and ground the draft in the right article. That change is
  measured on the held-out split before anyone rolls it out.
- Finding 4 names two small deterministic gaps, masked sensitive fields and the three-word
  minimum, for the red-teaming work to confirm and close.
- Finding 3 says the judge remains the only detector for rule extensions, and misses most of
  them; deferrals that name an outcome, which no draft here does, are left for the red-teaming
  work to provoke and for the promise patterns to back up.
