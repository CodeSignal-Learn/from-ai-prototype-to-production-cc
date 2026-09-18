# ADR 002: model access behind an interface, settings from the environment

## Status
Accepted at the start of production hardening.

## Context
The POC prototype talked to the model from a module that created the SDK client at import time,
hardcoded the model name, threshold, and token limits, and kept token
usage in a global. Tests could not import it without a key, nothing about it could be changed
between environments without editing code, and there was no way to run the pipeline offline.

## Decision
- `support_assistant/config.py` holds every runtime knob in an immutable `Settings` read once
  from `ASSISTANT_*` environment variables with validation. Command-line flags override it.
- `support_assistant/llm/` defines one `LLMClient` interface: `complete(system, user,
  max_tokens)` returning text and token usage. `LiveClient` implements it on the Anthropic SDK
  and is the only place that touches the SDK. `ReplayClient` serves recordings keyed by the
  exact prompt and fails loudly when one is missing. `RecordingClient` wraps a live client to
  produce those recordings. `ScriptedClient` exists for tests.
- `model.py` receives a client and puts instructions in the system prompt and customer text in
  the user message. It has no state.
- `pipeline.process_request` takes `Settings` and an optional client. Rules mode needs neither
  key nor client.

## Consequences
- Tests never contact the API. Unit tests use `ScriptedClient`; end-to-end runs use replay.
- A deployment changes model, thresholds, timeouts, and client through configuration.
- Recordings are prompt-exact: changing a prompt requires re-recording, which is the point.
- Rules-mode behavior is unchanged; the batch output at this commit is identical to the POC's.

## Not yet addressed
Timeouts are configured but nothing retries or falls back; the model's answer is still trusted;
the customer text still shares the user message with instructions to the model; batches run one
request at a time; there is no service interface and no version stamping. Each has its own unit.
