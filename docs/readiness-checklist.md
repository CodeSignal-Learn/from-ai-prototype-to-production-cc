# Production readiness checklist

State of the hardened assistant at the end of the hardening phase. Every closed item names its
evidence. Two gates stay open on purpose; release is not recommended until they close.

## Closed

| Area | Item | Evidence |
| --- | --- | --- |
| Architecture | Model access behind one interface; live, replay, and scripted clients | `support_assistant/llm/`, ADR 002, `tests/test_replay.py` |
| Architecture | Every runtime knob in validated settings from the environment | `config.py`, `tests/test_config.py` |
| Architecture | Rules mode works without the SDK installed and is identical to the POC control | `test_rules_mode_and_replay_do_not_need_the_sdk`; batch diff against v1 |
| Reliability | Timeouts from settings, SDK retries off, bounded retries with backoff | `llm/live.py`, `llm/retry.py`, `tests/test_retry.py` |
| Reliability | A failed model call never fails a request or a batch | `tests/test_failures.py`, `docs/failure-handling.md` |
| Reliability | Interrupted batches resume by request id | `--resume`, verified on 40 requests |
| Security | Instructions aimed at the assistant are escalated before any draft is requested | `tests/test_security.py`, REQ-2017 in `docs/trial-results-v2.md` |
| Security | Card numbers masked at intake; records validated; oversized bodies escalated | `tests/test_security.py` |
| Security | Instructions and customer text separated; tags cannot be closed by customers | `model.py`, `tests/test_security.py` |
| Security | Model verdicts validated; drafts checked for promises, numbers, and links | `security.py`, `tests/test_security.py` |
| Security | Request endpoints require the service key; health stays open; the server refuses to start without a key | `api.py`, `tests/test_api.py` |
| Performance | Bounded concurrency in the batch runner and the batch endpoint; the service measured under load, zero errors | `docs/load-report.md`, `results/load-replay-2s.json` |
| Operability | Health endpoint reports mode, client, model, and versions | `api.py`, `tests/test_api.py` |
| Operability | Every result carries app, prompt, model, and mode versions | `version.py`, `tests/test_version.py` |
| Operability | Rollback to rules mode by configuration, rehearsed | `docs/recovery-rehearsal.md` |
| Operability | Model outages can be injected for drills | `ASSISTANT_REPLAY_FAILURES`, `tests/test_version.py` |

## Open gates

| Gate | Why it is open | What closes it |
| --- | --- | --- |
| Semantic evaluation | The deterministic checks catch numbers, links, and promises. The two ungrounded statements found in the POC review were stated in words and would pass them. Nobody has measured how often the hardened prompts invent policy, on how many requests, with what held-out set | An evaluation suite: rubric, labeled dataset with a held-out split, a calibrated judge, adversarial cases, and a baseline versus candidate comparison |
| Monitoring | Nothing records or alerts on the rate of `classification_unavailable`, flagged drafts, latency, or cost in production. Version stamps exist but nothing reads them | Structured events, objectives, alerts, drift reports, and recurring evaluation |

## Known limits, not blocking hardening
- Confidence is uncalibrated (21 of 25 trial values at 0.95); escalation does not rely on it.
- Article selection inside a category is keyword-based and chose the wrong article for 5 of 25
  trial requests; the model then correctly deferred. To be measured and fixed with evaluation.
- Instruction detection matches phrasing; adversarial cases that go around it are for the
  evaluation suite to find.
- Load numbers come from a simulated model; live provider limits are unmeasured.
