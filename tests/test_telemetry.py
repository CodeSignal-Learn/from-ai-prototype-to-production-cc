"""Telemetry: every step of a request is an event with a duration and its tokens, on one trace,
carrying no customer or draft text. Clocks are injected; nothing here waits or calls the API."""
import json

import pytest

from support_assistant.config import Settings, validate
from support_assistant.llm.client import ScriptedClient
from support_assistant.llm.errors import LLMTimeout
from support_assistant.pipeline import process_batch, process_request
from support_assistant.telemetry.events import EventSink, read_events, text_fingerprint
from support_assistant.telemetry.metrics import estimate_cost, percentile, summarize
from support_assistant.telemetry.trace import Trace


class FakeClock:
    def __init__(self):
        self.now = 100.0

    def __call__(self):
        return self.now

    def advance(self, seconds):
        self.now += seconds


def verdict(category, confidence=0.9):
    return json.dumps({"category": category, "confidence": confidence, "reason": "scripted"})


def test_a_request_emits_one_trace_with_every_step(make_request, articles):
    sink = EventSink()
    clock = FakeClock()
    client = ScriptedClient([verdict("billing"), "Hi Test, the pending authorization drops off within five business days.\n\nFernwood Outfitters Support"])
    request = make_request("Charged twice", "two identical amounts left my account for one order")
    result = process_request(request, articles, Settings(mode="model", llm_client="replay"), client, sink=sink, clock=clock)
    steps = [(e.step, e.status) for e in sink.events]
    assert steps == [("request", "received"), ("classify", "ok"), ("lookup", "ok"), ("draft", "ok"), ("checks", "ok"), ("request", "ok")]
    assert len({e.trace_id for e in sink.events}) == 1
    assert all(e.request_id == request.id for e in sink.events)
    final = sink.events[-1]
    assert final.attrs["route"] == "draft" and final.attrs["category"] == "billing" and final.attrs["drafted"] is True
    assert final.attrs["versions"] == result.versions
    assert final.attrs["calls"] == 2


def test_events_carry_no_customer_or_draft_text(make_request, articles):
    sink = EventSink()
    body = "my card was charged twice for order 49250 and i want the money back"
    draft = "Hi Test, a pending authorization drops off within five business days.\n\nFernwood Outfitters Support"
    client = ScriptedClient([verdict("billing"), draft])
    process_request(make_request("Charged twice", body), articles, Settings(mode="model", llm_client="replay"), client, sink=sink)
    log = "\n".join(e.to_json() for e in sink.events)
    assert "charged twice" not in log.lower() and "49250" not in log and "pending authorization" not in log
    assert text_fingerprint(body)["sha256"] in log and str(len(body)) in log


def test_durations_come_from_the_injected_clock(make_request, articles):
    sink = EventSink()
    clock = FakeClock()

    class SlowClient(ScriptedClient):
        def complete(self, system, user, max_tokens):
            clock.advance(0.25)
            return super().complete(system, user, max_tokens)

    client = SlowClient([verdict("billing"), "Hi Test, thanks.\n\nFernwood Outfitters Support"])
    process_request(make_request("Charged twice", "two identical amounts left my account"), articles, Settings(mode="model", llm_client="replay"), client, sink=sink, clock=clock)
    by_step = {e.step: e for e in sink.events if e.step != "request"}
    assert by_step["classify"].duration_ms == 250.0
    assert by_step["draft"].duration_ms == 250.0
    assert by_step["lookup"].duration_ms == 0.0
    assert sink.events[-1].duration_ms == 500.0


def test_tokens_are_attributed_to_the_step_that_used_them(make_request, articles):
    sink = EventSink()
    client = ScriptedClient([verdict("billing"), "Hi Test, thanks for reaching out about the charge.\n\nFernwood Outfitters Support"])
    process_request(make_request("Charged twice", "two identical amounts left my account"), articles, Settings(mode="model", llm_client="replay"), client, sink=sink)
    by_step = {e.step: e for e in sink.events if e.step != "request"}
    assert by_step["classify"].attrs["calls"] == 1 and by_step["draft"].attrs["calls"] == 1
    assert by_step["classify"].attrs["input_tokens"] + by_step["draft"].attrs["input_tokens"] == sink.events[-1].attrs["input_tokens"]
    assert "calls" not in by_step["lookup"].attrs


def test_the_failure_path_is_recorded_and_the_request_still_completes(make_request, articles):
    sink = EventSink()
    client = ScriptedClient([LLMTimeout("t"), LLMTimeout("t"), LLMTimeout("t")])
    settings = Settings(mode="model", llm_client="replay", max_retries=2)
    result = process_request(make_request("Charged twice", "two identical amounts left my account"), articles, settings, client, sleep=lambda s: None, sink=sink)
    classify = next(e for e in sink.events if e.step == "classify")
    assert classify.status == "unavailable" and classify.attrs["attempts"] == 3 and classify.attrs["last_error"] == "LLMTimeout"
    assert result.route == "human_review" and "classification_unavailable" in result.reasons
    assert sink.events[-1].status == "escalated"
    assert [e.step for e in sink.events] == ["request", "classify", "lookup", "request"]


def test_a_flagged_draft_is_a_flagged_request(make_request, articles):
    sink = EventSink()
    client = ScriptedClient([verdict("billing"), "Hi Test, we will refund the 74.50 within 2 days.\n\nFernwood Outfitters Support"])
    process_request(make_request("Charged twice", "two identical amounts left my account"), articles, Settings(mode="model", llm_client="replay"), client, sink=sink)
    checks = next(e for e in sink.events if e.step == "checks")
    assert checks.status == "flagged" and checks.attrs["problems"]
    assert sink.events[-1].status == "flagged"


def test_a_declined_v2_draft_is_recorded(make_request, articles):
    sink = EventSink()
    client = ScriptedClient([json.dumps({"category": "billing", "confidence": 0.9, "article": "billing-and-invoices", "reason": "s"}), "NO_ANSWER"])
    process_request(make_request("Tax", "why was i charged sales tax"), articles, Settings(mode="model", llm_client="replay", prompt_variant="v2"), client, sink=sink)
    draft = next(e for e in sink.events if e.step == "draft")
    assert draft.status == "declined" and "draft" not in draft.attrs
    assert next(e for e in sink.events if e.step == "lookup").attrs["method"] == "model"
    assert sink.events[-1].status == "escalated" and "article_does_not_answer" in sink.events[-1].attrs["reasons"]


def test_rules_mode_emits_events_without_a_client(make_request, articles):
    sink = EventSink()
    process_request(make_request("Refund", "when will i get my refund for the boots"), articles, Settings(mode="rules"), sink=sink)
    assert [e.step for e in sink.events] == ["request", "classify", "lookup", "draft", "request"]
    assert next(e for e in sink.events if e.step == "classify").attrs["mode"] == "rules"
    assert "calls" not in sink.events[-1].attrs or sink.events[-1].attrs["calls"] == 0


def test_a_batch_writes_every_trace_to_the_file(make_request, articles, tmp_path):
    path = tmp_path / "events.jsonl"
    settings = Settings(mode="rules", concurrency=4, events_file=path)
    requests = [make_request(f"Refund {i}", "when will i get my refund for the boots") for i in range(6)]
    process_batch(requests, articles, settings)
    rows = read_events(path)
    assert len({r["trace_id"] for r in rows}) == 6
    assert sum(1 for r in rows if r["step"] == "request" and r["status"] == "ok") == 6
    assert all(r["schema"] == 1 for r in rows)


def test_metrics_are_recomputed_from_events(make_request, articles):
    sink = EventSink()
    clock = FakeClock()
    settings = Settings(mode="model", llm_client="replay", max_retries=0)
    ok = ScriptedClient([verdict("billing"), "Hi Test, thanks for the note.\n\nFernwood Outfitters Support"])
    process_request(make_request("Charged twice", "two identical amounts left my account"), articles, settings, ok, sink=sink, clock=clock)
    process_request(make_request("Charged twice", "two identical amounts left my account"), articles, settings, ScriptedClient([LLMTimeout("t")]), sleep=lambda s: None, sink=sink, clock=clock)
    rows = [json.loads(e.to_json()) for e in sink.events]
    summary = summarize(rows, input_rate=1.0, output_rate=5.0)
    assert summary["requests"] == 2 and summary["traces"] == 2
    assert summary["model_unavailable"] == 1 and summary["model_call_failures"] == 1
    assert summary["routes"] == {"draft": 1, "human_review": 1}
    assert summary["usage"]["calls"] == 2
    assert summary["cost"]["total_usd"] == estimate_cost(summary["usage"]["input_tokens"], summary["usage"]["output_tokens"], 1.0, 5.0)
    assert summarize(rows)["cost"] is None


def test_percentiles_and_cost_arithmetic():
    assert percentile([3, 1, 2], 50) == 2 and percentile([], 50) is None
    assert estimate_cost(1_000_000, 200_000, 1.0, 5.0) == 2.0
    assert estimate_cost(10, 10, None, 5.0) is None


def test_rates_must_be_set_together_and_non_negative():
    with pytest.raises(ValueError, match="set together"):
        validate(Settings(input_rate_per_million=1.0))
    with pytest.raises(ValueError, match="zero or more"):
        validate(Settings(input_rate_per_million=-1.0, output_rate_per_million=1.0))


def test_a_trace_records_an_exception_as_a_failed_step():
    sink = EventSink()
    trace = Trace("REQ-X", sink, FakeClock())
    with pytest.raises(RuntimeError):
        with trace.step("lookup"):
            raise RuntimeError("boom")
    assert sink.events[-1].status == "failed" and sink.events[-1].attrs["error"] == "RuntimeError"
