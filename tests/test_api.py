import json

import pytest
from fastapi.testclient import TestClient

from support_assistant.api import app_factory, create_app
from support_assistant.config import Settings
from support_assistant.llm.client import ScriptedClient

RECORD = {"id": "REQ-7001", "customer_name": "Ada Lovelace", "email": "ada@example.com",
          "subject": "Refund status", "body": "when will i get my refund for order 48102",
          "channel": "email", "created_at": "2026-08-01T00:00:00Z"}


def rules_client(articles):
    return TestClient(create_app(Settings(mode="rules"), articles))


def test_health_reports_mode_and_configuration(articles):
    response = TestClient(create_app(Settings(mode="rules", concurrency=4), articles)).get("/health")
    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "ok" and body["mode"] == "rules" and body["concurrency"] == 4 and body["articles"] == 9


def test_one_request_returns_a_result(articles):
    response = rules_client(articles).post("/requests", json=RECORD)
    assert response.status_code == 200
    result = response.json()
    assert result["id"] == "REQ-7001" and result["category"] == "returns_refunds" and result["route"] == "draft"
    assert result["sent"] is False


def test_invalid_record_is_a_400_not_a_crash(articles):
    response = rules_client(articles).post("/requests", json={**RECORD, "email": "nope"})
    assert response.status_code == 400
    assert "email" in response.json()["detail"]


def test_batch_returns_results_and_rejected_records(articles):
    records = [RECORD, {**RECORD, "id": "REQ-7002", "channel": "fax"}, {**RECORD, "id": "REQ-7003", "body": "help"}]
    response = rules_client(articles).post("/batches", json=records)
    assert response.status_code == 200
    body = response.json()
    assert [r["id"] for r in body["results"]] == ["REQ-7001", "REQ-7003"]
    assert body["rejected"][0]["index"] == 1
    assert "insufficient_information" in body["results"][1]["reasons"]


def test_oversized_batch_is_refused(articles):
    response = rules_client(articles).post("/batches", json=[RECORD] * 201)
    assert response.status_code == 413


def keyed_client(articles):
    return TestClient(create_app(Settings(mode="rules", api_key="test-key"), articles))


def test_requests_without_the_key_are_refused(articles):
    client = keyed_client(articles)
    assert client.post("/requests", json=RECORD).status_code == 401
    assert client.post("/batches", json=[RECORD]).status_code == 401


def test_a_wrong_key_is_refused_and_the_right_one_accepted(articles):
    client = keyed_client(articles)
    assert client.post("/requests", json=RECORD, headers={"X-API-Key": "wrong"}).status_code == 401
    response = client.post("/requests", json=RECORD, headers={"X-API-Key": "test-key"})
    assert response.status_code == 200 and response.json()["sent"] is False


def test_health_stays_open_and_serving_without_a_key_is_refused(articles, monkeypatch):
    assert keyed_client(articles).get("/health").status_code == 200
    monkeypatch.delenv("ASSISTANT_API_KEY", raising=False)
    with pytest.raises(RuntimeError, match="ASSISTANT_API_KEY"):
        app_factory()


def test_model_mode_uses_the_injected_client(articles):
    client = ScriptedClient([json.dumps({"category": "returns_refunds", "confidence": 0.9, "reason": "x"}), "Hi Ada, five business days."])
    app = create_app(Settings(mode="model", llm_client="replay"), articles, client)
    response = TestClient(app).post("/requests", json=RECORD)
    assert response.status_code == 200
    assert response.json()["draft"].startswith("Hi Ada")
    assert TestClient(app).get("/health").json()["llm_client"] == "replay"
