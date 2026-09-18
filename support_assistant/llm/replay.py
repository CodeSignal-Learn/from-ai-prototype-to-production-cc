import hashlib
import json
from pathlib import Path

from .client import Completion, LLMError, UsageTotals


class RecordingMissing(LLMError):
    """The replay client has no recording for this exact prompt."""


def recording_key(model: str, system: str, user: str, max_tokens: int) -> str:
    payload = json.dumps({"model": model, "system": system, "user": user, "max_tokens": max_tokens}, sort_keys=True)
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()[:24]


class ReplayClient:
    """Serves recorded completions keyed by the exact prompt. Deterministic, offline, free.

    A prompt with no recording raises RecordingMissing instead of guessing, so a changed prompt
    is noticed immediately.
    """

    def __init__(self, recordings_dir: Path, model: str):
        self.recordings_dir = Path(recordings_dir)
        self.model = model
        self.usage = UsageTotals()

    def complete(self, system: str, user: str, max_tokens: int) -> Completion:
        key = recording_key(self.model, system, user, max_tokens)
        path = self.recordings_dir / f"{key}.json"
        if not path.exists():
            raise RecordingMissing(f"no recording {key} for model {self.model} in {self.recordings_dir}")
        record = json.loads(path.read_text(encoding="utf-8"))
        completion = Completion(
            text=record["text"],
            input_tokens=record["input_tokens"],
            output_tokens=record["output_tokens"],
            model=record["model"],
        )
        self.usage.add(completion)
        return completion


class RecordingClient:
    """Wraps a real client and writes every completion to the recordings folder."""

    def __init__(self, inner, recordings_dir: Path):
        self.inner = inner
        self.model = inner.model
        self.recordings_dir = Path(recordings_dir)
        self.recordings_dir.mkdir(parents=True, exist_ok=True)

    @property
    def usage(self) -> UsageTotals:
        return self.inner.usage

    def complete(self, system: str, user: str, max_tokens: int) -> Completion:
        completion = self.inner.complete(system, user, max_tokens)
        key = recording_key(self.model, system, user, max_tokens)
        record = {
            "model": completion.model,
            "system": system,
            "user": user,
            "max_tokens": max_tokens,
            "text": completion.text,
            "input_tokens": completion.input_tokens,
            "output_tokens": completion.output_tokens,
        }
        (self.recordings_dir / f"{key}.json").write_text(json.dumps(record, ensure_ascii=False, indent=2), encoding="utf-8")
        return completion
