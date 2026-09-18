from ..config import Settings
from .client import LLMClient
from .errors import LLMMalformed, LLMRateLimited, LLMTimeout, LLMUnavailable
from .replay import ReplayClient

FAILURES = {
    "timeout": lambda: LLMTimeout("injected timeout"),
    "rate_limit": lambda: LLMRateLimited("injected rate limit"),
    "unavailable": lambda: LLMUnavailable("injected outage"),
    "malformed": lambda: LLMMalformed("injected malformed answer"),
}


def build_client(settings: Settings) -> LLMClient:
    """The one place that decides which client the application talks to."""
    if settings.llm_client == "replay":
        failures = [FAILURES[name]() for name in settings.replay_failures]
        return ReplayClient(settings.recordings_dir, settings.model, failures=failures,
                            latency_seconds=settings.replay_latency_seconds)
    from .live import LiveClient  # the SDK is only needed for live calls

    return LiveClient(settings.model, settings.timeout_seconds)
