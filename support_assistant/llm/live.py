from anthropic import APIConnectionError, APIError, APIStatusError, APITimeoutError, Anthropic, RateLimitError

from .client import Completion, LLMError, UsageTotals
from .errors import LLMRateLimited, LLMTimeout, LLMUnavailable


def map_sdk_error(error: Exception) -> LLMError:
    """Translate SDK exceptions into the application's error types.

    Timeouts, rate limits, connection problems, and provider-side 5xx errors are retryable.
    Anything else (bad request, authentication, not found) is a programming or deployment error
    and comes back as a plain LLMError so nobody retries it.
    """
    if isinstance(error, APITimeoutError):
        return LLMTimeout(str(error))
    if isinstance(error, RateLimitError):
        return LLMRateLimited(str(error))
    if isinstance(error, APIConnectionError):
        return LLMUnavailable(str(error))
    if isinstance(error, APIStatusError) and error.status_code >= 500:
        return LLMUnavailable(f"provider error {error.status_code}")
    return LLMError(f"{type(error).__name__}: {error}")


class LiveClient:
    """The Anthropic SDK behind the LLMClient interface.

    Credentials come from the environment (ANTHROPIC_API_KEY) through the SDK; nothing in the
    application reads the key. The SDK's own retries are turned off so the application's retry
    policy is the only one, and the timeout comes from settings.
    """

    def __init__(self, model: str, timeout_seconds: float):
        self.model = model
        self.usage = UsageTotals()
        self._client = Anthropic(timeout=timeout_seconds, max_retries=0)

    def complete(self, system: str, user: str, max_tokens: int) -> Completion:
        try:
            response = self._client.messages.create(
                model=self.model,
                max_tokens=max_tokens,
                system=system,
                messages=[{"role": "user", "content": user}],
            )
        except APIError as error:
            raise map_sdk_error(error) from error
        text = "".join(block.text for block in response.content if block.type == "text")
        completion = Completion(
            text=text,
            input_tokens=response.usage.input_tokens,
            output_tokens=response.usage.output_tokens,
            model=response.model,
        )
        self.usage.add(completion)
        return completion
