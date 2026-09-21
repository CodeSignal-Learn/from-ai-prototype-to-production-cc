# Production readiness checklist

State of the assistant after hardening and evaluation. Every closed item names its evidence.
One gate stays open; release is not recommended until it closes.

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
| Evaluation | Quality is defined and measured: rubric, 168-case dataset with a held-out split, runner with deterministic checks and a judge calibrated against a reviewer, 22 adversarial probes kept as regressions, baseline versus candidate comparison over repeated runs | `evals/`, `docs/eval-baseline.md`, `docs/judge-calibration.md`, `docs/failure-taxonomy.md`, `docs/eval-comparison.md` |
| Security | Paraphrased instructions found by red-teaming are detected; pasted card numbers reach a person; deferrals that name an outcome are treated as promises | `tests/test_regressions.py`, `docs/failure-taxonomy.md` |

## Open gates

| Gate | Why it is open | What closes it |
| --- | --- | --- |
| Monitoring | Nothing records or alerts on the rate of `classification_unavailable`, flagged drafts, latency, or cost in production. Version stamps exist but nothing reads them | Structured events, objectives, alerts, drift reports, and recurring evaluation |

## Known limits, not blocking
- Confidence is uncalibrated (21 of 25 trial values at 0.95); escalation does not rely on it.
- Article selection inside a category is keyword-based and chose the wrong article for 18 of 57
  answerable development cases (`docs/eval-baseline.md`, finding 2); the v2 candidate prompts
  address it and are pending the decision in `docs/eval-comparison.md`.
- A request the knowledge base does not answer receives a drafted deferral instead of an
  escalation (finding 1); same candidate, same decision.
- Instruction detection matches phrasing; the red-team probes run with every evaluation and the
  next paraphrase will show up there first.
- Load numbers come from a simulated model; live provider limits are unmeasured.
