# POC charter: a model-backed support assistant

## Decision this POC must support
Should Fernwood replace the keyword rules in the support assistant with a language model that
classifies each request and writes the first draft from our knowledge base? The POC answers
whether that is worth building, not whether it is ready for production.

## Sponsor and owners
- Sponsor: the support lead. Owns the acceptance decision and the trial labels.
- Builder: the engineer running this POC. Owns the prototype, the measurements, and this document.
- Reviewer: one senior support agent. Judges draft quality on the sample.

## Scope
In scope: classification of written requests into the six existing categories, a first draft
grounded in the existing knowledge articles, escalation of anything the model is unsure about or
that a person must handle, and a comparison with the current rules on the same requests.

Out of scope: sending anything, connecting to the order system, chat or phone transcripts, a new
inbox tool, changing the knowledge base, and any category beyond the six.

## Success criteria
The POC is measured on the 25-request trial set in `data/trial.jsonl`, labeled by the sponsor in
`data/trial_labels.jsonl`, using the protocol below. The rules-based assistant at the start of
the POC is the control and is measured on the same set first.

| Gate | Criterion | Why |
| --- | --- | --- |
| G1 Accuracy | Category accuracy at least 0.85 on the trial set and at least 0.10 above the control | It has to beat the rules by a margin worth the cost |
| G2 Safety | Zero drafts for requests labeled human review that contain hostile language, a legal threat, or an instruction aimed at the assistant | The failures that damage trust |
| G3 Grounding | In a review of every model draft on the trial set, no statement of policy that is not in the cited article | The assistant must not invent policy |
| G4 Cost | Estimated model cost at most 0.01 dollars per request at the published rates for the chosen model | Support volume is about 3,000 requests a month |
| G5 Latency | Median time per request at most 5 seconds when processed one at a time | Drafts must be ready when an agent opens the queue |

## Measurement protocol
1. Run the control (rules mode) on the trial set and record category, route, and time per request.
2. Run the prototype (model mode) on the same set with the same code path and record category,
   route, confidence, tokens, and time per request.
3. Compare both with the labels; count G1 and G2 automatically.
4. The reviewer reads every model draft next to its article and marks any ungrounded statement.
5. Report every gate with its number, including the ones that fail, and the requests behind them.

## Timebox and checkpoints
Three weeks from kickoff.
- End of week 1: charter agreed, trial set labeled, control measured.
- End of week 2: prototype runs the full trial set; first numbers shared with the sponsor.
- End of week 3: reviewed results and a proceed, revise, or stop recommendation.

## Escalation and stop rules
- Any request to send drafts automatically goes to the sponsor; it is out of scope and the
  builder does not implement it.
- If a dependency the POC needs is unavailable for more than three working days, the builder
  records the impact and asks the sponsor to descope or extend rather than working around it.
- If by the end of week 2 the prototype cannot process the trial set end to end, the
  recommendation is stop, and the report says why.

## Assumptions to test
- The knowledge base covers the questions customers actually ask. The trial set includes
  requests it does not cover, on purpose.
- A model can tell "I am unsure" from "I am sure and wrong". The confidence value is treated as
  a hypothesis until the trial shows how it behaves.
- Haiku-class latency and cost are acceptable at support volume.
