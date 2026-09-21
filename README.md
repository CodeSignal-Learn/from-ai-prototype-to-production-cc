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
ASSISTANT_PROMPT_VARIANT=v2 python3 -m support_assistant.cli data/requests.jsonl --mode model   # the candidate prompts (live)
python3 -m evals.report --baseline v1-held_out-baseline-r1 v1-held_out-baseline-r2 v1-held_out-baseline-r3 --candidate v1-held_out-candidate-r1 v1-held_out-candidate-r2 v1-held_out-candidate-r3
```

Settings are read from `ASSISTANT_*` environment variables (mode, model, client, prompt variant,
timeouts, retries, concurrency, folders, the API key); see `support_assistant/config.py`. Flags override them.
`ASSISTANT_PROMPT_VARIANT` is `v1` by default; `v2` selects the candidate prompts described in
`docs/eval-comparison.md`, which are not rolled out.

Documents for the POC engagement are in `docs/`: the charter, ADR 001, the decision log, the
trial results, and the go or no-go recommendation. The evaluation suite lives in `evals/`:
the rubric (`evals/rubric.md`), the versioned datasets, the runner, the judge, the judge
calibration, and the baseline-versus-candidate report; runs are written under `results/evals/`.
Evaluation findings are in `docs/eval-baseline.md`, `docs/judge-calibration.md`,
`docs/failure-taxonomy.md`, and `docs/eval-comparison.md`.

The requests in `data/` are synthetic samples; no real customer data is stored in this repository.
