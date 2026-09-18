from .client import LLMError


class LLMTimeout(LLMError):
    """The model did not answer within the configured time."""


class LLMRateLimited(LLMError):
    """The provider asked us to slow down."""


class LLMUnavailable(LLMError):
    """A connection problem or a provider-side error; retrying may help."""


class LLMMalformed(LLMError):
    """The model answered, but not in the shape we asked for."""


class LLMFailed(LLMError):
    """Every attempt allowed by the retry policy failed. Carries the last error."""

    def __init__(self, last_error: Exception, attempts: int):
        super().__init__(f"{attempts} attempt(s) failed; last error: {last_error}")
        self.last_error = last_error
        self.attempts = attempts
