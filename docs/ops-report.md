# Operational report: objectives and alerts

What the assistant promises in production, how each promise is measured from the event log, who
is told when it is broken, and what they do. Objectives are in `ops/objectives.json`, alert rules
in `ops/alert_rules.json`; both are evaluated by `ops/slo.py` and `ops/alerts.py` over tumbling
windows of an event log, and both were tested by replaying a week of recorded traffic twice:
once as it was, once with an outage and a slow stretch injected. Both tools read a finished log
and print what fired in it. Running them on the live log on a schedule, keeping each alert open
until it is resolved, and delivering it to its owner belong to the monitoring system the service
is deployed with; this project builds none of them.

## Two kinds of measurement

Everything in this document comes from events, and events are immediate: a request completed,
took this long, was escalated for these reasons, used these tokens. Whether the draft was any
good is a **delayed** measurement. It needs the article, the request, and a reader or a
calibrated judge, and it comes from the recurring evaluation, not from an event. The objectives
below therefore use two proxies the events do carry, the escalation share and the flagged-draft
share, and say so; a fall in quality that changes neither will only show in the scheduled
evaluation. That is the gap the drift work fills.

## The traffic

`data/traffic/week-1.jsonl`: 500 requests over seven days, business hours, about seven an hour,
sampled from the development cases so every request has a recording and a label. Replayed with
`scripts/replay_traffic.py`, which stamps events from each request's arrival time and advances a
simulated clock by a plausible model latency per call (spread deterministically, plus a per-token
term, plus the full timeout when a call times out and the retry backoff), so a week replays in
seconds and reads like a week. Replayed twice:

- `results/events/week-1.jsonl`: as recorded.
- `results/events/week-1-incidents.jsonl`: with an outage injected from the arrival of request
  200 to the arrival of request 210 (`--outage 200:210`: every model call from 15:51 to 17:38 on
  Wednesday times out, which hits the ten requests that arrive in it)
  and the base model latency raised from 2.4 s to 12 s for requests 320 to 359, which puts
  simulated calls at about 4 to 9 s against 1.2 to 2.7 s normally (a slow stretch of about five
  and a half hours from 12:32 on Friday, plus the first request on Saturday).

## Objectives

Daily windows, at least 20 requests each, rates $1.00 / $5.00 per million tokens.

| Objective | Indicator and target | Why |
| --- | --- | --- |
| Availability | share of requests that completed with no model step unavailable (a request that failed counts against it), at least 0.99 | An unavailable step still reaches a person, but costs the agent the draft; one in a hundred is what the team agreed to absorb |
| Latency | p95 of request duration at most 8 s | A drafted request took 2.4 s at the live median, two calls of about a second each; 8 s leaves room for retries on a minority of requests before agents notice |
| Escalation share | requests routed to a person at most 0.45 | The agents' workload, and the first place a change in the traffic mix shows |
| Flagged drafts | requests with a flagged draft, as a share of all requests, at most 0.10 | On the first recorded week the checks flagged 25 of 500 requests (5.9 percent of the 422 drafts), 2.8 to 9.9 percent of requests a day, 15 of them unverifiable promises and 10 ungrounded numbers; a rising rate is the signal, not the level |
| Spend | estimated cost per request at most $0.01 | The POC charter's cost gate, at operator-supplied rates; without rates it reports insufficient data |

`python3 -m ops.slo results/events/week-1.jsonl --input-rate 1.00 --output-rate 5.00`:

| Objective | Windows met | Values per day |
| --- | --- | --- |
| Availability | 7/7 | 1.000 every day |
| Latency p95 | 7/7 | 4,431 / 4,280 / 4,282 / 4,432 / 4,304 / 4,240 / 4,431 ms |
| Escalation share | 7/7 | 0.181 / 0.211 / 0.153 / 0.197 / 0.264 / 0.197 / 0.239 |
| Flagged drafts | 7/7 | 0.056 / 0.042 / 0.028 / 0.042 / 0.056 / 0.028 / 0.099 |
| Spend | 7/7 | $0.001 per request every day |

The same on the incident replay: availability 0.861 on Wednesday (missed), latency p95 61,500 ms
on Wednesday and 16,452 ms on Friday (missed), the other three objectives met. The Wednesday
p95 is the timeout: a request whose three classification attempts each wait out the 20 s
timeout takes over a minute to reach a person.

A target of 0.05 would be missed on three days of the clean week (0.056, 0.056, 0.099). The
target is 0.10 with its reason recorded, because the objective describes what the team accepts,
and the level it accepted changed when the checks got stricter: the outcome-deferral promise
patterns came from the evaluation work. An objective that is missed on an ordinary week
is either a wrong target or a real problem, and the report has to say which.

## Alert rules

| Rule | Condition | Persistence | Severity, owner | Respond |
| --- | --- | --- | --- | --- |
| model_unavailable | unavailable rate over 0.05 in a 60-minute window of at least 5 requests | 1 window | high, on-call engineer | Inspect the unavailable step events (attempts, last error), the provider's status, `/health`. If a second window follows, switch to rules mode per the runbook; back when two windows are clean |
| retries_rising | retry share over 0.2 in a 60-minute window of at least 5 requests | 2 consecutive | warning, on-call engineer | `failed_calls` and `last_error` on step events, latency p95, the provider's status. Lower concurrency for batch runs, confirm the rules-mode fallback is ready, watch the next window; if the unavailable rule fires next, switch on its first window |
| latency_p95 | p95 over 8 s in a 120-minute window of at least 8 requests | 2 consecutive | medium, on-call engineer | Per-step durations, output tokens, attempts. Pause batch runs or lower their concurrency, and raise the timeout within the objective; rules mode if it persists two more windows |
| escalation_share | over 0.60 in a 240-minute window of at least 20 requests | 2 consecutive | low, support lead | The reasons mix, the category mix against the baseline week, version changes. Open a drift investigation; roll nothing back on this alert alone |
| flagged_drafts | over 0.15 in a 120-minute window of at least 8 requests | 2 consecutive | medium, on-call engineer | Which checks fire, whether the prompt version or model alias changed. Pin the previous versions; confirm on the replay client |
| spend | over $0.01 per request in a daily window of at least 20 requests | 1 window | low, product owner | Tokens per step, the variant running. No automatic action |

Windows are sized to the volume: at seven requests an hour, a one-hour window rarely holds enough
requests to judge a percentile, so latency and flagged drafts use two-hour windows and escalation
share four-hour windows. Persistence (`for_windows`) is what separates a change from a blip: a
single bad window is recorded as noise in the alert history and pages nobody.

## Tested trigger behavior

`python3 -m ops.alerts results/events/week-1.jsonl --input-rate 1.00 --output-rate 5.00`: no
alerts fired. Over 154 hourly, 77 two-hourly, 39 four-hourly, and 7 daily windows, the only
condition that was ever true was flagged drafts in one two-hour window (noise, 1).

`python3 -m ops.alerts results/events/week-1-incidents.jsonl --input-rate 1.00 --output-rate 5.00`
(excerpt: the ALERT, windows, and open-first lines):

```text
ALERT HIGH model_unavailable at 2026-09-09T16:00+00:00  owner: on-call engineer
  windows: 15:00-16:00 value 0.1429 n=7
  open first: 86b8f64176bcc9af
ALERT MEDIUM latency_p95 at 2026-09-11T16:00+00:00  owner: on-call engineer
  windows: 12:00-14:00 value 16452.3 n=15; 14:00-16:00 value 16541.5 n=16
  open first: d69f330ca6f2db96, a8425c9ccf85d86f, 47880d5a621b4797
```

The outage fired the availability rule at 16:00, at the end of the first hour it touched (1 of 7
requests). The condition held for the next two hourly windows (5 of 5, then 4 of 10) without
re-paging, so the rule's response, rules mode when a second window follows, would have applied
from 17:00. It also pushed latency over the threshold for one two-hour window, which the latency
rule recorded as noise because the outage was over before a second window; the availability rule
owns outages, and the latency rule owns slowness that lasts. The Friday slow stretch fired the
latency rule at 16:00, at the end of its second two-hour window, three and a half hours after the
first slow request, with the three slowest traces as evidence. Escalation share reached 0.60 in
the Wednesday window from 16:00 to 20:00 (9 of 15 requests, against 0.07 on the clean replay),
because every request the outage hit went to a person; the window held fewer than the rule's 20
requests, so it was not judged. The slow stretch did not move it, because slowness does not
change routing.

The synthetic-log tests in `tests/test_ops.py` pin the mechanics: one bad window is noise and
two in a row fire; a third does not re-page; windows below the minimum request count never
count; the unavailable alert carries the affected traces as evidence; the shipped rule and
objective files load and reject a bad comparison or an unknown indicator; the clean week fires
nothing and the incident week fires exactly these two.

## What the alerts cannot see

- A prompt or model change that makes drafts worse without making them promise anything shows
  in none of these indicators. The recurring evaluation and the drift report are the detector.
- A change in the traffic mix that raises escalations looks like a fault and is not one. The
  escalation rule's response is an investigation for that reason.
- A request that never finishes, because the process stopped, has a `received` event and no
  final one, so it is in no window. Windows end at the last completed request, so a service that
  stops writing events produces no window at all. Both read as quiet traffic, and no rule here
  fires on them.
- The replay's durations are simulated. The rules were tuned to the live median of 2.4 s per
  drafted request (about one second a call) and the 20 s timeout; the live tail is unmeasured until the service runs on real traffic.
