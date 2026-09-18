# Recovery rehearsal

Performed on the hardened build before tagging it, on the author's laptop, against the API on
port 8765 with the replay client. Two drills: the model service fails, and a rollback to rules
mode. The request used is `docs/rehearsal/request-1023.json`. Output below is pasted from the
terminal; drafts are cut to 90 characters. The service key for the drill is `rehearsal-key`, set on
the server and sent by every `POST` as `X-API-Key`; `/health` needs none.

## Drill 1: the model service is down

Three consecutive timeouts are injected through `ASSISTANT_REPLAY_FAILURES`; the retry policy
allows three attempts, so the first request's classification runs out of retries. The retry
delay was lowered to 0.1 s for the drill.

```text
$ ASSISTANT_API_KEY=rehearsal-key ASSISTANT_MODE=model ASSISTANT_LLM_CLIENT=replay ASSISTANT_REPLAY_FAILURES=timeout,timeout,timeout uvicorn support_assistant.api:app_factory --factory --port 8765

$ curl -s http://127.0.0.1:8765/health
{
    "status": "ok",
    "mode": "model",
    "llm_client": "replay",
    "model": "claude-haiku-4-5",
    "concurrency": 1,
    "articles": 9,
    "versions": {
        "app": "2.0.0",
        "mode": "model",
        "model": "claude-haiku-4-5",
        "prompt": "81ec9d26f2c2",
        "client": "replay"
    }
}

$ curl -s -X POST http://127.0.0.1:8765/requests -H "Content-Type: application/json" -H "X-API-Key: rehearsal-key" -d @docs/rehearsal/request-1023.json   # first call: the injected outage
{
  "id": "REQ-1023",
  "category": "other",
  "route": "human_review",
  "reasons": [
    "classification_unavailable",
    "unknown_category",
    "no_reference_article"
  ],
  "draft": null,
  "confidence": null,
  "versions": {
    "app": "2.0.0",
    "mode": "model",
    "model": "claude-haiku-4-5",
    "prompt": "81ec9d26f2c2",
    "client": "replay"
  }
}

$ curl -s -X POST http://127.0.0.1:8765/requests -H "Content-Type: application/json" -H "X-API-Key: rehearsal-key" -d @docs/rehearsal/request-1023.json   # second call: recordings again
{
  "id": "REQ-1023",
  "category": "returns_refunds",
  "route": "draft",
  "reasons": [],
  "draft": "Hi Diego,\n\nThanks for reaching out. Since it's been three weeks since delivery, I'd like t...",
  "confidence": 0.95
}

$ ASSISTANT_API_KEY=rehearsal-key ASSISTANT_MODE=rules uvicorn support_assistant.api:app_factory --factory --port 8765   # rollback: same code, rules mode

$ curl -s http://127.0.0.1:8765/health
{
    "status": "ok",
    "mode": "rules",
    "llm_client": null,
    "model": null,
    "concurrency": 1,
    "articles": 9,
    "versions": {
        "app": "2.0.0",
        "mode": "rules",
        "model": null,
        "prompt": null,
        "client": null
    }
}

$ curl -s -X POST http://127.0.0.1:8765/requests -H "Content-Type: application/json" -H "X-API-Key: rehearsal-key" -d @docs/rehearsal/request-1023.json
{
  "id": "REQ-1023",
  "category": "returns_refunds",
  "route": "draft",
  "reasons": [],
  "draft": "Hi Diego,\n\nThanks for contacting Fernwood Outfitters about your refund timelines question....",
  "confidence": null,
  "versions": {
    "app": "2.0.0",
    "mode": "rules",
    "model": null,
    "prompt": null,
    "client": null
  }
}
```

## What the drills showed
- With the model unavailable, the request reached a person with `classification_unavailable`
  and no draft. The service answered normally; nothing crashed and nothing was sent.
- Once the injected failures were used up, the same request received a model draft again, with
  no operator action.
- Rolling back was one environment variable and a restart. `/health` reported `"mode": "rules"`
  with `prompt` and `model` cleared, and the same request came back with a rules draft. Both
  results carry version stamps, so a queue of mixed results is attributable.
- Time from the decision to roll back to a confirmed rules draft: under a minute.

## Not rehearsed
- Rollback under real traffic with agents in the queue.
- A partial outage with rate limits rather than timeouts; the code path is the same, but the
  timing differs.
- Recovery of an interrupted batch with `--resume` under an outage; verified separately on 40
  requests without failures.
