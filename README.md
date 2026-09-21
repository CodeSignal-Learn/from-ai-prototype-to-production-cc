# Fernwood Outfitters support-request assistant

Fernwood Outfitters is an outdoor-gear web store. This application helps its support
team handle written requests: it classifies each request, finds the relevant knowledge-base
passage, drafts a reply, and either queues the draft for human review or escalates the request.
The application never sends messages; a human always does.

## Running it

```bash
python3 -m pytest
python3 -m support_assistant.cli data/requests.jsonl
python3 -m support_assistant.cli data/requests.jsonl --mode model   # needs ANTHROPIC_API_KEY
python3 -m support_assistant.cli data/requests.jsonl --mode model --client replay --concurrency 4
python3 scripts/run_trial.py --mode rules
python3 scripts/run_trial.py --mode model --input-rate 1.00 --output-rate 5.00
python3 scripts/record.py data/requests.jsonl data/trial.jsonl      # refresh recordings (live)
ASSISTANT_API_KEY=<secret> uvicorn support_assistant.api:app_factory --factory   # GET /health; POST /requests, POST /batches need X-API-Key
ASSISTANT_API_KEY=<secret> python3 scripts/load_test.py --base-url http://127.0.0.1:8000 --concurrency 1 4 8
python3 -m evals.dataset v1                                            # validate the evaluation cases, print coverage
python3 -m evals.runner --dataset v1 --split development --client replay --label check   # score a split offline
python3 -m evals.calibration --run v1-development-baseline --human evals/datasets/v1/human_judgments.jsonl
ASSISTANT_PROMPT_VARIANT=v1 python3 -m support_assistant.cli data/requests.jsonl --mode model   # the previous prompts, the rollback (live)
python3 -m evals.report --baseline v1-held_out-baseline-r1 v1-held_out-baseline-r2 v1-held_out-baseline-r3 --candidate v1-held_out-candidate-r1 v1-held_out-candidate-r2 v1-held_out-candidate-r3
python3 -m support_assistant.cli data/requests.jsonl --mode model --client replay --events results/events/batch.jsonl   # write a trace per request
python3 -m support_assistant.telemetry.metrics results/events/batch.jsonl --input-rate 1.00 --output-rate 5.00        # latency, errors, usage, cost
python3 scripts/replay_traffic.py data/traffic/week-1.jsonl --events results/events/week-1.jsonl --variant v1 [--outage 200:30] [--slow 320:360:12000]   # the committed week logs are v1
python3 -m ops.slo results/events/week-1.jsonl --input-rate 1.00 --output-rate 5.00      # objectives over daily windows
python3 -m ops.alerts results/events/week-1-incidents.jsonl --input-rate 1.00 --output-rate 5.00   # which rules fire, for whom, what to do
python3 -m ops.drift --baseline results/events/week-1.jsonl --recent results/events/week-2.jsonl --out results/drift/week-2-vs-week-1.json
python3 -m ops.scheduled_eval --as-of 2026-09-20 --traffic data/traffic/week-2.jsonl --label 2026-09-20-week-2   # suites vs reference, window quality
python3 scripts/replay_traffic.py data/traffic/week-2.jsonl --events results/events/week-2-incident.jsonl --flaky 96:114:rate_limit --failures 118:12:timeout --rules-from 122:150   # the rehearsed incident
```

Settings are read from `ASSISTANT_*` environment variables (mode, model, client, prompt variant,
timeouts, retries, concurrency, folders, the API key); see `support_assistant/config.py`. Flags override them.
`ASSISTANT_PROMPT_VARIANT` is `v2` by default since app version 3.0.0 (`docs/eval-comparison.md`
for the comparison, `docs/optimization-experiment.md` for the rollout decision); `v1` is the shipped
prompt set and the rollback. `ASSISTANT_DRAFT_POLICY=skip_unnamed` is a measured and rejected
optimization, kept behind its setting.

Documents for the POC engagement are in `docs/`: the charter, ADR 001, the decision log, the
trial results, and the go or no-go recommendation. The evaluation suite lives in `evals/`:
the rubric (`evals/rubric.md`), the versioned datasets, the runner, the judge, the judge
calibration, and the baseline-versus-candidate report; runs are written under `results/evals/`.
Evaluation findings are in `docs/eval-baseline.md`, `docs/judge-calibration.md`,
`docs/failure-taxonomy.md`, and `docs/eval-comparison.md`. Every request emits a trace of
structured events (`support_assistant/telemetry/`, `docs/telemetry.md`), written to the file in
`ASSISTANT_EVENTS_FILE`; events carry no customer or draft text. `ops/` holds the service
objectives (`ops/objectives.json`) and alert rules (`ops/alert_rules.json`) evaluated over event
windows, with the report in `docs/ops-report.md`; `data/traffic/` holds two recorded weeks that
`scripts/replay_traffic.py` replays with simulated time. `ops/drift.py` compares two windows and
names investigation signals; `ops/scheduled_eval.py` re-runs the evaluation suites against their
reference runs, scores the cases behind a traffic window weighted by request counts, and records
every new failure (`docs/drift-report.md`). `ops/runbook.md` is what to do when an alert fires;
`docs/incident-2026-09-15.md` is a rehearsal of a provider outage, warned, contained in rules
mode, and compared with the same outage left alone. `docs/optimization-experiment.md` records the
v2 rollout on replayed traffic (adopted) and a call-saving draft policy (rejected).

The requests in `data/` are synthetic samples; no real customer data is stored in this repository.
