# Production readiness assessment of the POC prototype

Input: ADR 001's shortcut list, the trial findings in `docs/trial-results.md`, and a read of
the code at v1. Each gap has a priority and the unit of work that closes it.

| Priority | Gap | Evidence | Closed by |
| --- | --- | --- | --- |
| High | A request can carry instructions aimed at the assistant and nothing detects it | REQ-2017 drafted; the model resisted by luck | Security boundaries |
| High | The model's answer is trusted as returned: any category string, any confidence, any draft | ADR 001 shortcuts; the fenced-JSON crash | Security boundaries |
| High | A failed model call fails the whole batch; no timeout, retry, or fallback | ADR 001 shortcuts; SDK default 10 minute timeout | Failure handling |
| High | Instructions and customer text are concatenated in one message | `model.py` at v1 | Security boundaries |
| Medium | Model name, threshold, and token limits are hardcoded; the SDK client is created at import | `model.py` at v1; importing it constructs a client | This unit |
| Medium | No offline or deterministic way to run model mode | Trial reruns cost money and vary | This unit |
| Medium | Requests are processed one at a time; nothing is known about throughput or tail latency | 2.4 s median per request, sequential | Performance |
| Medium | Drafts can state policy the article does not contain | REQ-2020, REQ-2023 | Security boundaries (deterministic checks) and the evaluation course (semantic) |
| Medium | Nothing records which code, prompt, and model produced a result | Results carry no versions | Rollout and recovery |
| Low | Confidence is not calibrated and the threshold never fires | 21 of 25 at 0.95 | Evaluation course |
| Low | Article lookup inside a category is keyword-based and picked the wrong article 5 times | REQ-2003, 2004, 2007, 2009, 2025 | Evaluation course, after measurement |
| Low | Order-status answers need the order system | Decision D2 | Out of scope for this path |

Rules-mode behavior is the safety net throughout: a deployment can fall back to it by
configuration at any point.
