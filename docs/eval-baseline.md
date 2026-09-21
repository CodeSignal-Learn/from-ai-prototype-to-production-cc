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
| Expected article selected (8 of them: none expected, none selected) | 79 |
| Correct article, draft-expected cases | 39 of 57 |

Forty-five of the 62 unacceptable results come from two mechanisms: 32 drafted deferrals and 13
alphabetical tie-breaks. The POC trial showed both on a handful of requests (REQ-2024's drafted
deferral; five wrong-article deferrals) but was too small to count them.

## Finding 1: the assistant drafts when it should hand over

32 requests the label sends to a person received a draft. All 32 drafts defer ("a specialist
will follow up"); 23 are requests no article covers (20 labeled not covered, and three general
questions the labels put in `other`: a gift card balance, a site bug, down sourcing), 4 ask for an
action on an order, 3 are pre-sales questions, 2 carry a pasted card number. In most of them the
model notices that the article does not answer and writes a deferral, and the pipeline queues
that deferral as a draft; the two card-number requests are answered from the article and still
needed a person. The
agent then reads a draft that says nothing, and the request is not in the escalation queue
where it belongs. Nothing in the pipeline distinguishes "the article answered" from "the model
declined to answer"; both are drafts.

This is the largest single cause of routing failures (R1 fail 39, of which 32 are this) and it
is invisible to the deterministic checks, because a deferral promises nothing.

## Finding 2: the wrong article is selected inside the right category

18 of 57 draft-expected cases did not get the expected article, and 13 of them are one
mechanism. The keyword scorer in `knowledge.py` picks the article with the most keyword hits;
when no keyword hits, every article scores zero and the first in alphabetical order wins:
`account-merge` over `password-reset`, `order-tracking` over `shipping-times`, `product-care`
over `warranty-claims`, `refund-timelines` over `returns-policy`. Every keywordless sign-in
problem became an account-merge draft; every warranty question that used none of the warranty
article's keywords (a snapped pole, a lost tip, a broken strap holder) became a product-care
draft. The model then, correctly, said the article did not answer and deferred, so the customer
got no answer the team has. A fourteenth case, EV-3115, is the same tie-break in the wrong
category; two (EV-3105, EV-3109) picked the other article on a keyword hit; EV-3046 and EV-3068
were misclassified. The tie-break drafts are 13 of the 21 R4 fails and most of the
acceptable-rate gap in `product_issue` and `returns_refunds`.

## Finding 3: unsupported statements are about as common as the POC review found, and mostly of two shapes

17 drafts carry a statement the judge found unsupported. On the calibrated sample, five of the
judge's eleven R3 fails hold up when read, and it missed one real fail in 33 passes, so the true
count is nearer 10 than 17: about one draft in nine, close to the POC review's two in twenty. The
ones that hold up are extensions of a stated rule to a case it does not cover ("even after
cancellation", EV-3023; a summed delivery range, EV-3090; EV-3109) and deferrals that name an
outcome ("get you the correct women's medium fleece", EV-3007; "get you a corrected invoice",
EV-3045; "We'll get this sorted for you!", EV-3106). The judge missed one more of this shape,
EV-3055's "help you change your name in the system". Two more state a capability or policy the
article does not have (EV-3057 on shared accounts; EV-3002, invoices by email). The rest are the
judge's known errors: plain deferrals (EV-3042, EV-3094, EV-3119, EV-3121, EV-3135) and hedged
inferences (EV-3021, EV-3028, EV-3059). The drafting prompt's "use only facts stated in the
article" holds for most facts and slips on inferences.

## Finding 4: the deterministic checks and labels catch what they were built for

- The five hostile and three legal cases, the two instruction cases, and seven of the eight
  too-short bodies went to a person on the rule meant for them (the one oversized body is in the
  held-out split and was not run). The eighth,
  EV-3162, "it doesn't work", clears the three-word minimum; it reached a person only because the
  model classified it `other`, not because anything noticed it was unanswerable.
- The two pasted card numbers were masked at intake and the drafts repeat nothing; but neither
  request reached a person. `sensitive_data_masked` is a flag with no routing consequence.
- Two over-escalations: one two-topic request classified `other`, and EV-3090, where the draft
  check `ungrounded_number` fired on a summed "3-6 business days". The check did its job.
- Eleven R5 fails: ten are forbidden phrases. Nine are drafts that name the uncovered topic
  while deferring ("doesn't address sales tax", "shipping to Chile", "passkeys"), which the v1
  phrase lists were too broad to allow; v1 is left as is and these nine are read as label noise,
  not draft failures. The tenth, EV-3045's "get you a corrected invoice", is a real outcome
  promise, and the judge fails it under R3 as well. The eleventh is EV-3090.

## What this changes

- Findings 1 and 2 are the candidates for a revised prompt: let the model say that the article
  does not answer, and let it pick the article from the category's list, so the pipeline can
  route a non-answer to a person and ground the draft in the right article. That change is
  measured on the held-out split before anyone rolls it out.
- Finding 4 names two small deterministic gaps, masked sensitive fields and the three-word
  minimum, for the red-teaming unit to confirm and close.
- Finding 3 says the deterministic promise patterns should also cover deferrals that name an
  outcome, and that the judge remains the only detector for rule extensions.
