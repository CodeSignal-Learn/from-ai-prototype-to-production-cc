"""SDK exceptions map to the application's error types. No network."""
from anthropic import APIConnectionError, APITimeoutError, BadRequestError, InternalServerError, RateLimitError
import httpx2

from support_assistant.llm.client import LLMError
from support_assistant.llm.errors import LLMRateLimited, LLMTimeout, LLMUnavailable
from support_assistant.llm.live import map_sdk_error

REQUEST = httpx2.Request("POST", "https://api.anthropic.com/v1/messages")


def status_error(cls, code):
    response = httpx2.Response(code, request=REQUEST)
    return cls("boom", response=response, body=None)


def test_timeout_maps_to_retryable_timeout():
    assert isinstance(map_sdk_error(APITimeoutError(request=REQUEST)), LLMTimeout)


def test_rate_limit_maps_to_retryable_rate_limit():
    assert isinstance(map_sdk_error(status_error(RateLimitError, 429)), LLMRateLimited)


def test_connection_problem_maps_to_unavailable():
    assert isinstance(map_sdk_error(APIConnectionError(request=REQUEST)), LLMUnavailable)


def test_provider_error_maps_to_unavailable():
    assert isinstance(map_sdk_error(status_error(InternalServerError, 503)), LLMUnavailable)


def test_bad_request_is_not_retryable():
    error = map_sdk_error(status_error(BadRequestError, 400))
    assert type(error) is LLMError
