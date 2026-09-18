import pytest

from support_assistant.config import Settings, load_settings


def test_defaults_when_nothing_is_set():
    settings = load_settings(env={})
    assert settings.mode == "rules"
    assert settings.llm_client == "live"
    assert settings.model == "claude-haiku-4-5"
    assert settings.timeout_seconds == 20.0


def test_environment_overrides_defaults():
    settings = load_settings(env={"ASSISTANT_MODE": "model", "ASSISTANT_LLM_CLIENT": "replay", "ASSISTANT_TIMEOUT_SECONDS": "5", "ASSISTANT_CONCURRENCY": "4"})
    assert settings.mode == "model"
    assert settings.llm_client == "replay"
    assert settings.timeout_seconds == 5.0
    assert settings.concurrency == 4


@pytest.mark.parametrize("env", [
    {"ASSISTANT_MODE": "magic"},
    {"ASSISTANT_LLM_CLIENT": "cache"},
    {"ASSISTANT_CONFIDENCE_THRESHOLD": "1.5"},
    {"ASSISTANT_TIMEOUT_SECONDS": "0"},
    {"ASSISTANT_CONCURRENCY": "0"},
])
def test_invalid_values_are_rejected(env):
    with pytest.raises(ValueError):
        load_settings(env=env)


def test_settings_are_immutable():
    with pytest.raises(Exception):
        Settings().mode = "model"  # type: ignore[misc]


def test_rules_mode_and_replay_do_not_need_the_sdk(monkeypatch):
    import builtins
    import sys

    real_import = builtins.__import__

    def refuse_anthropic(name, *args, **kwargs):
        if name == "anthropic":
            raise ModuleNotFoundError("No module named 'anthropic'")
        return real_import(name, *args, **kwargs)

    for module in [m for m in sys.modules if m.startswith("support_assistant")]:
        del sys.modules[module]
    monkeypatch.setattr(builtins, "__import__", refuse_anthropic)
    from support_assistant.llm.factory import build_client

    client = build_client(Settings(mode="model", llm_client="replay"))
    assert type(client).__name__ == "ReplayClient"
