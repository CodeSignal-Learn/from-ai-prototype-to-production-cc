import pytest

from support_assistant.llm.client import LLMError
from support_assistant.llm.errors import LLMFailed, LLMMalformed, LLMRateLimited, LLMTimeout
from support_assistant.llm.retry import RetryPolicy, call_with_retry


class Flaky:
    def __init__(self, failures):
        self.failures = list(failures)
        self.attempts = 0

    def __call__(self):
        self.attempts += 1
        if self.failures:
            raise self.failures.pop(0)
        return "ok"


def test_succeeds_after_transient_failures_with_backoff():
    slept = []
    operation = Flaky([LLMTimeout("t"), LLMRateLimited("r")])
    result = call_with_retry(operation, RetryPolicy(max_retries=2, base_delay_seconds=0.5), sleep=slept.append)
    assert result == "ok"
    assert operation.attempts == 3
    assert slept == [0.5, 1.0]


def test_gives_up_after_the_last_allowed_attempt():
    slept = []
    operation = Flaky([LLMTimeout("1"), LLMTimeout("2"), LLMTimeout("3")])
    with pytest.raises(LLMFailed) as info:
        call_with_retry(operation, RetryPolicy(max_retries=2), sleep=slept.append)
    assert info.value.attempts == 3
    assert isinstance(info.value.last_error, LLMTimeout)
    assert len(slept) == 2


def test_non_retryable_errors_are_raised_at_once():
    slept = []
    operation = Flaky([LLMError("bad request")])
    with pytest.raises(LLMError):
        call_with_retry(operation, RetryPolicy(max_retries=5), sleep=slept.append)
    assert operation.attempts == 1
    assert slept == []


def test_malformed_answers_are_retried():
    operation = Flaky([LLMMalformed("not json")])
    assert call_with_retry(operation, RetryPolicy(max_retries=1), sleep=lambda s: None) == "ok"


def test_zero_retries_means_one_attempt():
    operation = Flaky([LLMTimeout("t")])
    with pytest.raises(LLMFailed):
        call_with_retry(operation, RetryPolicy(max_retries=0), sleep=lambda s: None)
    assert operation.attempts == 1


def test_delay_is_capped():
    policy = RetryPolicy(max_retries=10, base_delay_seconds=1.0, max_delay_seconds=4.0)
    assert [policy.delay(n) for n in range(1, 6)] == [1.0, 2.0, 4.0, 4.0, 4.0]
