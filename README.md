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
python3 scripts/run_trial.py --mode rules
python3 scripts/run_trial.py --mode model --input-rate 1.00 --output-rate 5.00
```

Documents for the POC engagement are in `docs/`: the charter, ADR 001, the decision log, the
trial results, and the go or no-go recommendation.

The requests in `data/` are synthetic samples; no real customer data is stored in this repository.
