# Failure handling

What happens when the model service misbehaves, decided per failure and tested without waiting.

| Failure | Detected by | Policy | Outcome for the request |
| --- | --- | --- | --- |
| No answer within the timeout | `LiveClient` raises `LLMTimeout` (SDK timeout from settings, SDK retries off) | Retry with backoff 0.5 s, 1 s, up to `max_retries` | Draft if a retry succeeds; otherwise a person, with `classification_unavailable` or `draft_unavailable` |
| Rate limited (429) | `LLMRateLimited` | Same retry | Same |
| Connection problem or provider 5xx | `LLMUnavailable` | Same retry | Same |
| Answer is not JSON, or JSON but not an object | `parse_json_answer` raises `LLMMalformed` | Same retry (asking again usually works) | Same |
| Bad request, authentication, not found (4xx other than 429) | plain `LLMError` | No retry; raised to the caller | The run stops. These are deployment or code errors and must be fixed, not retried |
| Classification worked, drafting failed | `LLMFailed` from the draft step | As above | Category kept, route becomes human review with `draft_unavailable` |
| The whole batch is interrupted | Operator | `--resume` skips ids already in the output file and appends | No request is processed twice into the same file |

## Duplicate work
Retrying a model call repeats a read-only request; nothing downstream happens until a person acts
on a draft, so a retried call cannot cause a duplicate side effect. Batch resume is keyed by
request id and appends only requests that are absent from the output file.

## Time
`RetryPolicy` computes delays; the sleep function is injected. Tests pass `lambda s: None` and
assert on the delays that would have been slept. End-to-end failure paths run offline: `ScriptedClient`
scripts exceptions between answers, and `ReplayClient(failures=[...])` raises them before serving a recording.

## Still open
- A run of repeated `classification_unavailable` results is a signal nobody sees yet; alerts
  belong to the operations course.
- Latency and cost of retries are not measured. Instrumentation comes with observability.
- Results are written only when the batch finishes, so a run that dies halfway has nothing on disk
  and starts over. Writing each result as it arrives belongs to the rollout work.
