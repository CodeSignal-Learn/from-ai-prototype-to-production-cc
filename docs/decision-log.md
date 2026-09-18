# POC decision log

Every change to scope, plan, or assumptions during the POC, with its effect on the charter and
the timebox. Newest last.

## D1. Request to send "safe" drafts automatically

Week 1, from the support lead after seeing the first rules-mode drafts.

Request: let drafts for simple categories go out without an agent's approval to shorten queue
time.

Impact if accepted: removes the property the charter is built on (nothing is sent without a
person), changes what the trial measures, and adds sending infrastructure the POC does not have.

Decision: declined for the POC, per the charter's escalation rule. Raised with the sponsor as a
separate product question to decide after the trial, with the trial's grounding results as input.
No change to code, charter, or timebox.

## D2. Order-status answers need live order data

Week 1, found while labeling the trial set. Requests like REQ-2005 (where is my order) and
REQ-2020 (change the delivery address) cannot be fully answered from the knowledge base; they
need the order system.

Impact: the order system has no API the POC can call inside the timebox, and the charter already
leaves connecting to it out of scope. Working around it with a mock would make the trial measure
something that does not exist.

Decision: descope, per the charter's dependency rule. Order-status questions are answered from
the tracking article, and a request that needs someone to act on an order, such as an address
change, is labeled for a person; the trial measures whether the prototype sends it there.
Recorded as a limitation in the trial report. No change to code or charter. Timebox unchanged.

## D3. The model does not return bare JSON

Week 2. The first full trial run stopped on the first request: the model wrapped its JSON in a
Markdown code fence and the prototype parsed the answer as returned. The charter's assumption
list did not include the answer format.

Impact: half a day. Without a change, the trial cannot run end to end and the stop rule applies
at the end of week 2.

Decision: tolerate a fence around the JSON, and treat an answer that still does not parse as no
answer, so the request goes to a person with zero confidence. This is not output validation; a
well-formed answer with a category outside the six is still trusted. Proper validation stays on
the shortcut list in ADR 001 for production hardening. Timebox unchanged.
