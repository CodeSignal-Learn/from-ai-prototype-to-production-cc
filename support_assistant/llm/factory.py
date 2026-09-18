from ..config import Settings
from .client import LLMClient
from .replay import ReplayClient


def build_client(settings: Settings) -> LLMClient:
    """The one place that decides which client the application talks to."""
    if settings.llm_client == "replay":
        return ReplayClient(settings.recordings_dir, settings.model, latency_seconds=settings.replay_latency_seconds)
    from .live import LiveClient  # the SDK is only needed for live calls

    return LiveClient(settings.model, settings.timeout_seconds)
