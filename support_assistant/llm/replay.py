import hashlib
import json
import time
from pathlib import Path

from .client import Completion, LLMError, UsageTotals


class RecordingMissing(LLMError):
    """The replay client has no recording for this exact prompt."""


def recording_key(model: str, system: str, user: str, max_tokens: int, salt: str = "") -> str:
    """Stable key for one prompt. The salt separates repeated live runs of the same prompt, so a
    variability study keeps every repeat; an empty salt keeps every existing key unchanged."""
    payload = {"model": model, "system": system, "user": user, "max_tokens": max_tokens}
    if salt:
        payload["salt"] = salt
    return hashlib.sha256(json.dumps(payload, sort_keys=True).encode("utf-8")).hexdigest()[:24]


class ReplayClient:
    """Serves recorded completions keyed by the exact prompt. Deterministic, offline, free.

    A prompt with no recording raises RecordingMissing instead of guessing, so a changed prompt
    is noticed immediately.
    """

    def __init__(self, recordings_dir: Path, model: str, failures: list | None = None,
                 latency_seconds: float = 0.0, sleep=time.sleep, salt: str = ""):
        self.recordings_dir = Path(recordings_dir)
        self.model = model
        self.salt = salt
        self.usage = UsageTotals()
        # Failure injection: exceptions raised, in order, before any recording is served.
        self.failures = list(failures or [])
        # Simulated model latency, so offline load tests behave like the real thing.
        self.latency_seconds = latency_seconds
        self._sleep = sleep

    def complete(self, system: str, user: str, max_tokens: int) -> Completion:
        if self.failures:
            raise self.failures.pop(0)
        if self.latency_seconds:
            self._sleep(self.latency_seconds)
        key = recording_key(self.model, system, user, max_tokens, self.salt)
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
    """Wraps a real client and writes every completion to the recordings folder.

    A prompt that already has a recording is served from it instead of being sent again, so a
    recording run that stops halfway can be restarted without paying twice, and a run over a
    partly changed prompt set only records what changed. `replayed` counts the served ones.
    """

    def __init__(self, inner, recordings_dir: Path, reuse_existing: bool = True, salt: str = ""):
        self.inner = inner
        self.model = inner.model
        self.salt = salt
        self.recordings_dir = Path(recordings_dir)
        self.recordings_dir.mkdir(parents=True, exist_ok=True)
        self.reuse_existing = reuse_existing
        self.replayed = 0

    @property
    def usage(self) -> UsageTotals:
        return self.inner.usage

    def complete(self, system: str, user: str, max_tokens: int) -> Completion:
        key = recording_key(self.model, system, user, max_tokens, self.salt)
        path = self.recordings_dir / f"{key}.json"
        if self.reuse_existing and path.exists():
            record = json.loads(path.read_text(encoding="utf-8"))
            self.replayed += 1
            return Completion(text=record["text"], input_tokens=record["input_tokens"],
                              output_tokens=record["output_tokens"], model=record["model"])
        completion = self.inner.complete(system, user, max_tokens)
        record = {
            "model": completion.model,
            "salt": self.salt,
            "system": system,
            "user": user,
            "max_tokens": max_tokens,
            "text": completion.text,
            "input_tokens": completion.input_tokens,
            "output_tokens": completion.output_tokens,
        }
        (self.recordings_dir / f"{key}.json").write_text(json.dumps(record, ensure_ascii=False, indent=2), encoding="utf-8")
        return completion
