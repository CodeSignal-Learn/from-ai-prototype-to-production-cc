# Load report: the API under bounded concurrency

## Setup
- Server: `uvicorn support_assistant.api:app_factory --factory`, one process, on the author's
  laptop, with `ASSISTANT_MODE=model`, `ASSISTANT_LLM_CLIENT=replay`,
  `ASSISTANT_REPLAY_LATENCY_SECONDS=2`, and the service key set. Every model call answers from a recording after a
  simulated two-second wait, close to the 2.4 s median measured live in the trial. A drafted
  request makes two model calls, so its floor is about four seconds.
- Client: `scripts/load_test.py`, 24 requests per level cycled from `data/requests.jsonl`,
  sent to `POST /requests` with 1, 4, 8, and 16 in flight. Raw numbers in
  `results/load-replay-2s.json`.
- What this measures: how the service behaves when the model is slow and requests arrive
  together. What it does not measure: the real model service's rate limits or its latency
  under our load, which only a live test can show.

## Results
| In flight | Wall time for 24 | Throughput | p50 | p95 | p99 | Errors |
| --- | --- | --- | --- | --- | --- | --- |
| 1 | 96.4 s | 0.25 req/s | 4.01 s | 4.02 s | 4.03 s | 0 |
| 4 | 24.1 s | 0.99 req/s | 4.02 s | 4.02 s | 4.02 s | 0 |
| 8 | 12.1 s | 1.99 req/s | 4.02 s | 4.03 s | 4.03 s | 0 |
| 16 | 8.1 s | 2.97 req/s | 4.03 s | 4.03 s | 4.03 s | 0 |

Batch runner, same simulated latency: 40 requests with `--concurrency 4` took 40.2 s; the
first 8 requests one at a time took 32.2 s, so the full 40 would take about 160 s sequentially.
Results of the concurrent and the sequential batch are identical line for line.

## Reading the numbers
- Latency per request is the model's latency, twice. Nothing the service does adds measurable
  time; p99 sits 20 ms above p50 at every level.
- Throughput scales with concurrency because the work is waiting on the model, not computing.
  Sixteen in flight gave 2.97 requests per second against a floor of 0.25.
- The scaling is a property of the simulation. Against the live model service, more concurrency
  means more requests per minute at the provider, and the provider's rate limit, not this server,
  decides where throughput stops. The retry policy turns a 429 into a delay, not an error, so the
  symptom of too much concurrency will be rising p95, not failures.

## Capacity statement
At current support volume, about 3,000 requests a month, or roughly one every three minutes
across 160 working hours (one every 15 minutes around the clock), a single process at
concurrency 1 is more than enough: a request takes about four seconds. A backlog of 100 requests
clears in about seven minutes at concurrency 1 and under a minute at 8 with a two-second model.
Bounded concurrency of 4 for batch runs is the recommended default; raise it only after a live
test shows the provider tolerates it.

## Not tested
- Live provider behavior under concurrency (rate limits, latency variance).
- Tail latency. With 24 requests per level, p95 and p99 are the largest observed values, not
  estimates of production tail latency; that needs hundreds of requests per level, live.
- Memory or CPU pressure: the workload is I/O bound and the process stayed idle.
- More than one server process.
