"""Bounded retries with exponential backoff.

Time is injected so tests run instantly and so nothing here sleeps for real unless a caller
asks for it. Only errors that retrying can plausibly fix are retried.
"""
import time
from dataclasses import dataclass
from typing import Callable

from .errors import LLMFailed, LLMMalformed, LLMRateLimited, LLMTimeout, LLMUnavailable

RETRYABLE = (LLMTimeout, LLMRateLimited, LLMUnavailable, LLMMalformed)


@dataclass(frozen=True)
class RetryPolicy:
    max_retries: int = 2
    base_delay_seconds: float = 0.5
    max_delay_seconds: float = 8.0

    def delay(self, attempt: int) -> float:
        """Delay before retry number `attempt` (1 for the first retry): 0.5 s, 1 s, 2 s, ..."""
        return min(self.base_delay_seconds * (2 ** (attempt - 1)), self.max_delay_seconds)


def call_with_retry(operation: Callable[[], object], policy: RetryPolicy, sleep: Callable[[float], None] = time.sleep):
    """Run `operation`; on a retryable error wait and try again, at most policy.max_retries times.

    Raises LLMFailed after the last allowed attempt, and re-raises a non-retryable error at once.
    """
    attempts = policy.max_retries + 1
    for attempt in range(1, attempts + 1):
        try:
            return operation()
        except RETRYABLE as error:
            if attempt == attempts:
                raise LLMFailed(error, attempts) from error
            sleep(policy.delay(attempt))
    raise AssertionError("unreachable")
