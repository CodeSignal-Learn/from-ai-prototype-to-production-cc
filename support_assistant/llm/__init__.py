"""Model access behind one interface: a live client on the Anthropic SDK and a replay client
that serves recorded answers. The rest of the application only sees LLMClient.

LiveClient is imported from support_assistant.llm.live on demand, so rules mode and the replay
client work without the SDK installed.
"""
from .client import Completion, LLMClient, LLMError, ScriptedClient, UsageTotals
from .errors import LLMFailed, LLMMalformed, LLMRateLimited, LLMTimeout, LLMUnavailable
from .replay import RecordingClient, RecordingMissing, ReplayClient
from .retry import RetryPolicy, call_with_retry

__all__ = [
    "Completion", "LLMClient", "LLMError", "ScriptedClient", "UsageTotals",
    "LLMFailed", "LLMMalformed", "LLMRateLimited", "LLMTimeout", "LLMUnavailable",
    "RecordingClient", "RecordingMissing", "ReplayClient", "RetryPolicy", "call_with_retry",
]
