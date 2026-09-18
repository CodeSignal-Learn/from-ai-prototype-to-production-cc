from anthropic import APIError, Anthropic

from .client import Completion, LLMError, UsageTotals


class LiveClient:
    """The Anthropic SDK behind the LLMClient interface.

    Credentials come from the environment (ANTHROPIC_API_KEY) through the SDK; nothing in the
    application reads the key. The SDK's own retries are turned off so the application's retry
    policy is the only one.
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
            raise LLMError(f"{type(error).__name__}: {error}") from error
        text = "".join(block.text for block in response.content if block.type == "text")
        completion = Completion(
            text=text,
            input_tokens=response.usage.input_tokens,
            output_tokens=response.usage.output_tokens,
            model=response.model,
        )
        self.usage.add(completion)
        return completion
