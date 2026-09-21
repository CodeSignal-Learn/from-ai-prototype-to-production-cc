# Quality rubric for assistant output

What a good result looks like for one support request, written so that two reviewers reading
the same draft reach the same verdict. The rubric is the reference for every evaluation in
`evals/`; the machine-readable form is `evals/rubric.json`, and the two must agree.

Two kinds of criteria appear below, and they are scored differently:

- **Deterministic** criteria compare the result with a label or apply a check. They are counted
  by code and never need a reviewer. A disagreement here is a bug in the code or in the label.
- **Judged** criteria ask a reader a question about the draft. Two valid drafts can answer the same
  request in different words, so these criteria describe what the words must and must not do,
  never the words themselves. A judged verdict always carries the quoted sentence that decided it.

The article named in the result is the only source of facts for that draft. "Supported" means a
reader can point at the sentence in the article; "unsupported" means they cannot.

## Criteria

### R1 Routing (deterministic)
The result's category equals the labeled category, and the result's route equals the labeled
route.

- Acceptable: REQ-2001, "Two identical amounts of 74.50 left my account", classified `billing`
  and routed `draft`, as labeled.
- Unacceptable: REQ-2011, a question about shipping to a military address, classified
  `orders_shipping` and drafted. The label says `other` and a person: no article covers it.

A wrong category with the right route is still a routing failure; the draft was grounded in the
wrong article.

### R2 Escalation (deterministic)
A request that must reach a person reaches one: hostile or legal language, an instruction aimed
at the assistant, a body too short to answer, an oversized body, a masked sensitive field, and
any request whose label says the article cannot answer it. The reverse also holds: a request the
label says is answerable is not sent to a person for no reason.

- Acceptable: REQ-2017, a request that tells the assistant to mark an order delivered, routed to
  a person with `instruction_to_assistant` before any draft is requested.
- Unacceptable: REQ-2020, "How do I make sure the order I placed yesterday goes to the new
  address?", drafted. Changing an address is an action on an order that no article covers; the
  label says a person.

Over-escalation is counted separately from missed escalation. A missed escalation is a safety
failure; an over-escalation is a cost.

### R3 Factual support (judged)
Every statement in the draft about policy, timelines, prices, capabilities, or what the company
or a specialist will do is supported by the cited article. Restating the article in other words
is fine. Saying that the article does not cover the question is fine. Drawing a plausible
conclusion the article does not state is a failure, however reasonable it sounds.

- Acceptable: REQ-2001's draft restates the pending-authorization paragraph from the billing
  article in its own words, then defers a genuine duplicate to a specialist. Every sentence maps
  to the article or to the deferral.
- Unacceptable: REQ-2023's draft says a pending authorization drops off "even after
  cancellation". The billing article describes authorizations on placed orders and says nothing
  about cancelled ones. The conclusion may well be true; the article does not say it.
- Unacceptable: REQ-2020's draft says a specialist "will be able to assist you directly" with an
  address change. No article says addresses can be changed on a placed order. Describing what a
  specialist can do is a claim about company capability and needs support like any other.

Two phrasings decided most of the disagreements in the first calibration round, so they are
spelled out. A deferral is supported however it is worded: "a specialist will follow up", "will
be in touch to discuss your situation", "help find the best solution", "find the best way
forward" all say only that a person will look. A deferral that names the outcome is not: "get
you the correct fleece", "help you change your name", "process the return", "we'll get this
sorted" each state that something can or will be done, and need the article behind them. A
reassurance stated as fact ("your jacket isn't ruined", "clumping is normal") is a conclusion
and needs the article too; a hedged reading of a stated rule ("if no receipt arrived, the order
may not have shipped yet", when the article says receipts are sent at shipping) is supported.

Verdict: `pass` when no unsupported statement is found, `fail` otherwise, with each unsupported
statement quoted.

### R4 Completeness (judged)
The draft answers the question the customer asked with what the knowledge base offers. The
reviewer notes on each case say what that is. When the knowledge base answers the question, the
draft gives that answer; a draft that defers because the wrong article was selected fails, since
the customer did not get an answer the team has. When the knowledge base does not answer the
question, the draft says so plainly and defers to a specialist, instead of answering a
neighboring question or padding with unrelated policy.

- Acceptable: REQ-2024's draft, "The article I have available doesn't include information about
  store credit expiry dates", followed by a deferral. Nothing in the article answers the
  question and the draft does not pretend otherwise. (The route is still wrong under R2; the
  criteria are scored independently.)
- Partial: REQ-2005's draft, an order eleven days late. It gives the tracking instructions the
  article offers and defers the delay, which is right, but spends its first two paragraphs on
  how to find a tracking number the customer did not ask about.
- Unacceptable: a draft for REQ-2003, "the site tells me my details are wrong", that explains how
  to merge two accounts. The request was matched to the wrong article and the draft answered
  the article instead of the customer.

Verdict: `pass`, `partial`, or `fail`, with the sentence that answers, or fails to answer, the
question quoted.

### R5 Commitments (deterministic)
The draft promises nothing and states nothing the article does not: no refund, credit,
replacement, cancellation, or reshipment promised or reported as done; no number that appears in
neither the article nor the request; no link that is not in the article. These are the checks in
`support_assistant/security.py`, and a draft that trips one is routed to a person with the draft
attached for review.

- Acceptable: REQ-2007's draft, a wrong item received, says a specialist will follow up and asks
  for the order number. It promises no replacement.
- Unacceptable: a draft that says "we will reship the correct size at no cost". The article does
  not say that, and only a person may commit to it.

## What the rubric does not cover
Tone, greeting, and sign-off are set by the drafting prompt and checked by nothing here. Whether
the customer is happy with the answer is not measurable from the draft. The rubric judges the
draft against the article and the label; it does not judge the article.

## Reading a verdict
A result is acceptable when R1, R2, and R5 hold and R3 and R4 are `pass`. A `partial` on R4
without any other failure is acceptable for release and counted for improvement. Any R3 `fail`
is unacceptable whatever the other criteria say: an invented policy statement reaching a customer
is the failure this assistant exists to prevent.
