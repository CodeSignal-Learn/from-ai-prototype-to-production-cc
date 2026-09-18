"""Runtime settings, read from the environment in one place.

Every knob the prototype hardcoded lives here with a default, so a deployment changes behavior
through configuration and the code stays the same between environments.
"""
import os
from dataclasses import dataclass
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


@dataclass(frozen=True)
class Settings:
    mode: str = "rules"                      # rules | model
    llm_client: str = "live"                 # live | replay
    model: str = "claude-haiku-4-5"
    confidence_threshold: float = 0.6
    timeout_seconds: float = 20.0
    max_retries: int = 2
    retry_base_delay_seconds: float = 0.5
    concurrency: int = 1
    replay_latency_seconds: float = 0.0    # simulated model latency for offline load tests
    replay_failures: tuple[str, ...] = ()  # failures the replay client raises first, e.g. ("timeout", "timeout")
    recordings_dir: Path = ROOT / "fixtures" / "recordings"
    knowledge_dir: Path = ROOT / "kb"
    api_key: str | None = None             # required to serve the API; requests carry it in X-API-Key


def load_settings(env=None) -> Settings:
    """Build Settings from environment variables prefixed ASSISTANT_; unset ones keep defaults."""
    env = os.environ if env is None else env
    defaults = Settings()

    def pick(name, cast, default):
        raw = env.get(f"ASSISTANT_{name}")
        return default if raw is None or raw == "" else cast(raw)

    settings = Settings(
        mode=pick("MODE", str, defaults.mode),
        llm_client=pick("LLM_CLIENT", str, defaults.llm_client),
        model=pick("MODEL", str, defaults.model),
        confidence_threshold=pick("CONFIDENCE_THRESHOLD", float, defaults.confidence_threshold),
        timeout_seconds=pick("TIMEOUT_SECONDS", float, defaults.timeout_seconds),
        max_retries=pick("MAX_RETRIES", int, defaults.max_retries),
        retry_base_delay_seconds=pick("RETRY_BASE_DELAY_SECONDS", float, defaults.retry_base_delay_seconds),
        concurrency=pick("CONCURRENCY", int, defaults.concurrency),
        replay_latency_seconds=pick("REPLAY_LATENCY_SECONDS", float, defaults.replay_latency_seconds),
        replay_failures=pick("REPLAY_FAILURES", lambda raw: tuple(part.strip() for part in raw.split(",") if part.strip()), defaults.replay_failures),
        recordings_dir=pick("RECORDINGS_DIR", Path, defaults.recordings_dir),
        knowledge_dir=pick("KNOWLEDGE_DIR", Path, defaults.knowledge_dir),
        api_key=pick("API_KEY", str, defaults.api_key),
    )
    validate(settings)
    return settings


def validate(settings: Settings) -> None:
    if settings.mode not in ("rules", "model"):
        raise ValueError(f"ASSISTANT_MODE must be rules or model, got {settings.mode!r}")
    if settings.llm_client not in ("live", "replay"):
        raise ValueError(f"ASSISTANT_LLM_CLIENT must be live or replay, got {settings.llm_client!r}")
    if not 0.0 <= settings.confidence_threshold <= 1.0:
        raise ValueError("ASSISTANT_CONFIDENCE_THRESHOLD must be between 0 and 1")
    if settings.timeout_seconds <= 0:
        raise ValueError("ASSISTANT_TIMEOUT_SECONDS must be positive")
    if settings.max_retries < 0:
        raise ValueError("ASSISTANT_MAX_RETRIES must be zero or more")
    if settings.retry_base_delay_seconds < 0:
        raise ValueError("ASSISTANT_RETRY_BASE_DELAY_SECONDS must be zero or more")
    if settings.concurrency < 1:
        raise ValueError("ASSISTANT_CONCURRENCY must be at least 1")
    if settings.replay_latency_seconds < 0:
        raise ValueError("ASSISTANT_REPLAY_LATENCY_SECONDS must be zero or more")
    unknown = [name for name in settings.replay_failures if name not in ("timeout", "rate_limit", "unavailable", "malformed")]
    if unknown:
        raise ValueError(f"ASSISTANT_REPLAY_FAILURES has unknown failure names: {', '.join(unknown)}")
