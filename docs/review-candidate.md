# Review of the legal-escalation candidate

Reviewed against `CLAUDE.md` and the request: "escalate anything that threatens legal action".

## Accepted
- `escalation.py`: `LEGAL_TERMS` and the `legal_threat` reason. Matches the request; REQ-1037 now
  goes to human review instead of receiving a billing draft.
- `tests/test_escalation.py`: the new legal-threat test.

## Rejected
- `pipeline.py` and `notify.py`: drafts in "low-risk" categories were marked sent and posted to a
  webhook. Nobody asked for sending; drafts are never sent (CLAUDE.md, Boundaries). 20 of 40
  batch results came back with `sent: true`.
- `requirements.txt`: adds `requests`. No new dependencies, and it existed only to support the
  sending above.
- `intake.py`: normalization stopped lowercasing. Routing keywords depend on it; REQ-1025 fell
  from `returns_refunds` to `other` in the batch and the change was not part of the request.
- `tests/test_drafting.py`: `test_result_is_never_sent` was rewritten to accept any boolean. A
  failing test was the signal, not the problem. Restored.

## Requested correction
Keep only the escalation change and its test. Restore `pipeline.py`, `intake.py`, and the
original test; remove `notify.py` and `requirements.txt`.

## Evidence
- `python3 -m pytest`: 15 passed after correction.
- `python3 -m support_assistant.cli data/requests.jsonl`: REQ-1037 `human_review (legal_threat)`,
  REQ-1025 back to `returns_refunds`, no result with `sent: true`.
