# Production readiness checklist

State of the assistant at app version 3.0.0, after hardening, evaluation, and the operations
work. Every closed item names its evidence. One gate stays open, and only live traffic closes it.

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
| Observability | Every request emits a trace of structured events with step durations, token usage, failed attempts, versions, and cost from explicit rates; events carry no customer or draft text | `support_assistant/telemetry/`, `docs/telemetry.md`, `tests/test_telemetry.py` |
| Operations | Five objectives and six alert rules over event windows, each with an owner, evidence to inspect, and a response; tested on a clean week and a week with injected incidents | `ops/objectives.json`, `ops/alert_rules.json`, `docs/ops-report.md`, `tests/test_ops.py` |
| Operations | Drift between traffic windows reported as investigation signals; the suites re-run on a schedule against their reference runs and every regression is kept | `ops/drift.py`, `ops/scheduled_eval.py`, `docs/drift-report.md`, `tests/test_drift.py` |
| Operations | A provider outage rehearsed end to end: warning an hour ahead, containment in rules mode by configuration, recovery verified, impact compared with the same outage uncontained | `ops/runbook.md`, `docs/incident-2026-09-15.md` |
| Release | The v2 prompts adopted after a held-out comparison and a replayed rollout; a call-saving policy measured and rejected; `v1` is the rollback | `docs/eval-comparison.md`, `docs/optimization-experiment.md` |

## Open gates

| Gate | Why it is open | What closes it |
| --- | --- | --- |
| Live traffic | Every number in this checklist comes from recorded traffic replayed with simulated latency and from recordings of the model. The live tail latency, the provider's real failure shape, and how agents work the v2 queue are unmeasured | The first live week: the objectives report and the alert history on real events, and the scheduled evaluation on the week's cases |

## Known limits, not blocking
- Confidence is uncalibrated (21 of 25 trial values at 0.95); escalation does not rely on it.
- Under v2 the classifier names the article and declines when none answers, which closed the
  wrong-article and drafted-deferral findings on the held-out split and on replayed traffic
  (`docs/optimization-experiment.md`). Its action list still names account deletion, which the
  knowledge base covers; fixing the wording is a new candidate and needs a new held-out set.
- The escalation-share objective was re-baselined to 0.75 for v2's behavior; agents' experience
  of fewer drafts and more labeled escalations is unmeasured until the first live week.
- Instruction detection matches phrasing; the red-team probes run with every evaluation and the
  next paraphrase will show up there first.
- Load numbers come from a simulated model; live provider limits are unmeasured.
