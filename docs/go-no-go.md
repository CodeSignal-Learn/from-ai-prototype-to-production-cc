# Recommendation: revise, then proceed to hardening

For the support lead and the engineering lead. Evidence in `docs/trial-results.md`.

## The question
Should Fernwood replace the keyword rules with a model that classifies requests and writes the
first draft from the knowledge base?

## The answer in one paragraph
Yes to the approach, not yet to the prototype. On the 25 trial requests the model got the
category right 24 times against 9 for the rules, drafted 20 replies against 4, cost about a
tenth of a cent per request, and answered in under three seconds. Two of the charter's five
gates failed, both on safety: one request written to manipulate the assistant received a draft,
and two of twenty drafts stated policy that is not in our articles. Those are exactly the risks
the charter said would decide the outcome, and they are fixable with known engineering, not with
more prototyping. Recommendation: revise the prototype against the three conditions below, then
proceed to a production-hardening phase. Do not put the prototype in front of agents as it is.

## Gate by gate
| Gate | Outcome | What it means |
| --- | --- | --- |
| G1 Accuracy 0.96 vs 0.36 | Pass | On this set the model understands phrasings the keywords never will; the approach is shown to work on these 25 requests |
| G2 Safety, one guard case drafted | Fail | REQ-2017 carried an instruction aimed at the assistant. The model happened not to follow it. Nothing detected it |
| G3 Grounding, two ungrounded statements | Fail | REQ-2020 invented a capability, REQ-2023 extrapolated a policy. Agents reading every draft might catch these; nobody has measured that, and at volume the review thins |
| G4 Cost, 0.11 cents per request | Pass | About 3.30 dollars a month at current volume, at Haiku rates |
| G5 Latency, 2.4 s median | Pass | Well inside the queue refresh |

## Conditions for proceeding
1. Requests that contain instructions aimed at the assistant are detected and sent to a person,
   independently of the model's own judgment.
2. Drafts are checked against their article before they reach the queue, and the reviewer's
   sample review becomes a standing measurement rather than a one-time exercise.
3. Article selection is fixed. Five drafts deferred to a specialist only because the keyword
   lookup picked the wrong article inside the right category; the model had the category right.

## What the trial does not tell us
- Confidence is not a useful signal yet: 20 of 25 values were 0.95, and the one wrong category
  came at 0.85. The threshold never fired. Escalation must not depend on it until it is calibrated.
- 25 requests are enough to decide direction, not to size error rates. The hardening phase
  needs a larger labeled set and a held-out portion.
- Nothing has been measured about behavior under load, failures of the model service, or
  repeated runs of the same request.

## Cost of the alternatives
- Stop: keep the rules and the 84 percent of trial requests (21 of 25) they send to a person.
- Ship the prototype as is: cheaper this month, and the first invented policy or followed
  instruction that reaches a customer costs more than the project.
- Revise and harden: the shortcut list in ADR 001 is the work plan, plus the three conditions
  above. Estimate before committing a timeline; this document does not.

## Owners and next actions
- Support lead: decide on this recommendation; own the larger labeled set.
- Engineering lead: scope the hardening phase from ADR 001's shortcut list and the conditions.
- Builder: hand over the prototype, the trial harness, and this record; nothing is deployed.
