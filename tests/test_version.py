from support_assistant import model
from support_assistant.config import Settings
from support_assistant.intake import parse_request
from support_assistant.pipeline import process_request
from support_assistant.version import APP_VERSION, prompt_version, versions


def test_every_result_says_what_produced_it(articles):
    request = parse_request({"id": "REQ-1", "customer_name": "A B", "email": "a@example.com", "subject": "Refund",
                             "body": "when will i get my refund for the boots", "channel": "email", "created_at": "2026-08-01T00:00:00Z"})
    result = process_request(request, articles, Settings(mode="rules"))
    assert result.versions == {"app": APP_VERSION, "mode": "rules", "model": None, "prompt": None, "prompt_variant": None, "client": None}


def test_model_mode_versions_include_model_prompt_and_client():
    stamped = versions(Settings(mode="model", llm_client="replay"))
    assert stamped["model"] == "claude-haiku-4-5" and stamped["client"] == "replay"
    assert len(stamped["prompt"]) == 12


def test_prompt_version_changes_when_a_prompt_changes(monkeypatch):
    before = prompt_version()
    monkeypatch.setattr(model, "DRAFT_SYSTEM", model.DRAFT_SYSTEM + " Be brief.")
    assert prompt_version() != before


def test_failure_names_from_the_environment_build_injected_failures():
    from support_assistant.config import load_settings
    from support_assistant.llm.factory import build_client

    settings = load_settings(env={"ASSISTANT_MODE": "model", "ASSISTANT_LLM_CLIENT": "replay", "ASSISTANT_REPLAY_FAILURES": "timeout, unavailable"})
    client = build_client(settings)
    assert [type(f).__name__ for f in client.failures] == ["LLMTimeout", "LLMUnavailable"]
