import pytest

from support_assistant.llm.client import ScriptedClient
from support_assistant.llm.replay import RecordingClient, RecordingMissing, ReplayClient, recording_key


def test_recording_then_replay_returns_the_same_completion(tmp_path):
    live = ScriptedClient(["recorded answer"], model="fake-model")
    recorder = RecordingClient(live, tmp_path)
    first = recorder.complete("system text", "user text", max_tokens=50)

    replay = ReplayClient(tmp_path, model="fake-model")
    second = replay.complete("system text", "user text", max_tokens=50)
    assert second.text == first.text == "recorded answer"
    assert second.input_tokens == first.input_tokens
    assert replay.usage.calls == 1


def test_missing_recording_raises_instead_of_guessing(tmp_path):
    replay = ReplayClient(tmp_path, model="fake-model")
    with pytest.raises(RecordingMissing):
        replay.complete("system text", "never recorded", max_tokens=50)


def test_key_changes_when_any_prompt_part_changes():
    base = recording_key("m", "s", "u", 10)
    assert recording_key("m", "s", "u", 11) != base
    assert recording_key("m", "s2", "u", 10) != base
    assert recording_key("m2", "s", "u", 10) != base
