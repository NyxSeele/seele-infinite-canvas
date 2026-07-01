"""Agent LLM 调用容错：错误分类 + 指数退避重试（仅包裹 LLM 请求层）。"""

from __future__ import annotations

import asyncio
import logging
from typing import Any

import httpx
from openai import (
    APIConnectionError,
    APITimeoutError,
    AuthenticationError,
    BadRequestError,
    InternalServerError,
    RateLimitError,
)

logger = logging.getLogger(__name__)


def classify_llm_error(exc: Exception) -> tuple[bool, str]:
    """返回 (可重试, 用户可见文案)。"""
    if isinstance(exc, AuthenticationError):
        return False, "AI 服务认证失败，请检查 API Key 配置"
    if isinstance(exc, BadRequestError):
        return False, "请求无法处理，请简化或调整输入后重试"
    if isinstance(exc, RateLimitError):
        return True, "AI 服务暂时不可用，请稍后再试"
    if isinstance(exc, (APIConnectionError, APITimeoutError)):
        return True, "网络波动，请重试"
    if isinstance(exc, InternalServerError):
        return True, "AI 服务暂时不可用，请稍后再试"
    if isinstance(
        exc,
        (
            httpx.ConnectError,
            httpx.ReadTimeout,
            httpx.WriteTimeout,
            httpx.ConnectTimeout,
            httpx.PoolTimeout,
        ),
    ):
        return True, "网络波动，请重试"

    status_code = getattr(exc, "status_code", None)
    if isinstance(status_code, int):
        if status_code == 429:
            return True, "AI 服务暂时不可用，请稍后再试"
        if status_code >= 500:
            return True, "AI 服务暂时不可用，请稍后再试"
        if status_code == 401:
            return False, "AI 服务认证失败，请检查 API Key 配置"
        if status_code == 400:
            return False, "请求无法处理，请简化或调整输入后重试"

    lowered = str(exc).lower()
    if "connection error" in lowered or "connect" in lowered or "timeout" in lowered:
        return True, "网络波动，请重试"
    if "429" in lowered or "rate limit" in lowered:
        return True, "AI 服务暂时不可用，请稍后再试"

    return False, "AI 服务暂时不可用，请稍后再试"


def retry_delay_seconds(attempt: int, base_delay: float, *, rate_limited: bool) -> float:
    """attempt 从 0 开始；第 1 次重试前等待 base，第 2 次 2*base…"""
    delay = base_delay * (2**attempt)
    if rate_limited:
        delay = max(delay, 3.0)
    return delay


def is_rate_limited(exc: Exception) -> bool:
    if isinstance(exc, RateLimitError):
        return True
    status_code = getattr(exc, "status_code", None)
    return status_code == 429


async def sleep_before_retry(attempt: int, base_delay: float, exc: Exception) -> None:
    delay = retry_delay_seconds(attempt, base_delay, rate_limited=is_rate_limited(exc))
    logger.warning(
        "agent llm retry in %.1fs (attempt %s): %s",
        delay,
        attempt + 2,
        exc,
    )
    await asyncio.sleep(delay)
