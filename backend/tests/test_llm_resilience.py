from openai import APIConnectionError

from services.llm_resilience import classify_llm_error, retry_delay_seconds


def test_classify_connection_error_retryable():
    retryable, msg = classify_llm_error(APIConnectionError(request=None))
    assert retryable is True
    assert "网络" in msg


def test_classify_auth_not_retryable():
    exc = Exception("401 Unauthorized")
    exc.status_code = 401
    retryable, msg = classify_llm_error(exc)
    assert retryable is False
    assert "API Key" in msg


def test_classify_rate_limit_retryable():
    exc = Exception("429 rate limit")
    exc.status_code = 429
    retryable, msg = classify_llm_error(exc)
    assert retryable is True
    assert "暂时不可用" in msg


def test_retry_delay_backoff():
    assert retry_delay_seconds(0, 1.0, rate_limited=False) == 1.0
    assert retry_delay_seconds(1, 1.0, rate_limited=False) == 2.0
    assert retry_delay_seconds(0, 1.0, rate_limited=True) >= 3.0


def test_is_llm_quota_exhausted_error_detects_quota_and_429():
    from services.llm_resilience import is_llm_quota_exhausted_error

    exc_429 = Exception("429 Too Many Requests")
    exc_429.status_code = 429
    assert is_llm_quota_exhausted_error(exc_429)

    assert is_llm_quota_exhausted_error(Exception("免费额度已用尽"))
    assert is_llm_quota_exhausted_error(Exception("AllocationQuota exceeded"))

    assert not is_llm_quota_exhausted_error(Exception("401 Unauthorized"))
