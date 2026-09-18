# Rollout and rollback plan

For when the two open gates in `docs/readiness-checklist.md` are closed. Written now so the
hardening phase leaves a plan, not a hope.

## Principle
Rules mode is the safe state. It is the same code, selected by `ASSISTANT_MODE=rules`, needs no
key and no network, and produced the drafts the team used before. Every stage below can return
to it with a configuration change and a restart, in under a minute, without a deploy.

## Versions
Every result and the health endpoint carry `app`, `prompt`, `model`, `mode`, and `client`. A
rollout is a change to one of these. Two versions never run at once without the results saying
which is which.

## Stages
| Stage | What runs | Who sees model drafts | Exit criterion | Rollback trigger |
| --- | --- | --- | --- | --- |
| 1 Shadow | Model mode on a copy of the day's requests, offline, results compared with the rules results | Nobody | One week of shadow results; `classification_unavailable` under 1 percent; flagged-draft rate known | None needed; shadow has no users |
| 2 Canary | Two deployments of the same build: one in model mode receiving only the canary category (returns_refunds, a strong article set), one in rules mode receiving the rest; the support tool's queue routes each request by category, because `ASSISTANT_MODE` selects a mode per process | Two named agents on the canary category | Two weeks; the agents' rejection rate for model drafts no higher than for rules drafts | Any invented policy reaching a customer; rejection rate above rules for three days |
| 3 Expand | Model mode for all categories except `other` | The whole team | Evaluation suite (open gate) passes on the held-out set; monitoring (open gate) live | Same as canary, plus alert thresholds from the monitoring work |

Stage 3 does not start until both open gates are closed. Stages 1 and 2 can run before, because
in both a person reviews every draft and the rules path remains available.

## Rollback procedure
1. Set `ASSISTANT_MODE=rules` in the environment and restart the service.
2. Confirm `/health` reports `"mode": "rules"` and the expected `app` version.
3. Send one known request and confirm a rules draft comes back.
4. Record the time, the trigger, and the versions that were running, in the decision log.
Rehearsed on the hardened build: `docs/recovery-rehearsal.md`.

## Checks before each stage
- `python3 -m pytest` on the exact commit.
- Batch run on the replay client matches the committed results.
- `/health` versions match the commit's prompt version.
- The rollback procedure has been rehearsed on this version.

## Owners
- Support lead decides stage transitions and owns the rollback trigger thresholds.
- Engineering lead owns the environment configuration and the restart.
- Builder owns the evidence for exit criteria.
