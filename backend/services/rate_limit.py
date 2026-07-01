"""限流（Redis 优先，无 Redis 时内存降级）。"""

from __future__ import annotations

import threading
import time
from collections import defaultdict, deque

from fastapi import HTTPException, Request

from core.config import settings
from services.redis_client import get_redis

_lock = threading.Lock()
_ip_hits: dict[str, deque[float]] = defaultdict(deque)
_user_hits: dict[int, deque[float]] = defaultdict(deque)


def _prune(queue: deque[float], now: float, window: float) -> None:
    cutoff = now - window
    while queue and queue[0] <= cutoff:
        queue.popleft()


def _check_memory_bucket(
    bucket: dict[str | int, deque[float]],
    key: str | int,
    *,
    limit: int,
    window: float,
) -> None:
    now = time.monotonic()
    with _lock:
        queue = bucket[key]
        _prune(queue, now, window)
        if len(queue) >= limit:
            raise HTTPException(status_code=429, detail="请求过于频繁，请稍后再试")
        queue.append(now)


def _check_redis_bucket(key: str, *, limit: int, window: int = 60) -> None:
    r = get_redis()
    if r is None:
        return
    count = int(r.incr(key))
    if count == 1:
        r.expire(key, window)
    if count > limit:
        raise HTTPException(status_code=429, detail="请求过于频繁，请稍后再试")


def _client_ip(request: Request) -> str:
    forwarded = (request.headers.get("x-forwarded-for") or "").split(",")[0].strip()
    if forwarded:
        ip = forwarded
    else:
        client = request.client
        ip = (client.host if client else "unknown") or "unknown"
    if ip in ("::1", "localhost"):
        return "127.0.0.1"
    return ip


def clear_rate_limit_keys() -> int:
    """清除 Redis 中全部限流计数（开发排障用）。"""
    r = get_redis()
    if r is None:
        with _lock:
            _ip_hits.clear()
            _user_hits.clear()
        return 0
    deleted = 0
    for key in r.scan_iter("ratelimit:*"):
        deleted += int(r.delete(key))
    return deleted


def check_ip_rate_limit(request: Request) -> None:
    ip = _client_ip(request)
    limit = int(settings.rate_limit_per_minute)
    r = get_redis()
    if r is not None:
        _check_redis_bucket(f"ratelimit:ip:{ip}", limit=limit)
        return
    _check_memory_bucket(_ip_hits, ip, limit=limit, window=60.0)


def check_user_rate_limit(user_id: int) -> None:
    limit = int(settings.rate_limit_user_per_minute)
    r = get_redis()
    if r is not None:
        _check_redis_bucket(f"ratelimit:user:{user_id}", limit=limit)
        return
    _check_memory_bucket(_user_hits, int(user_id), limit=limit, window=60.0)


def check_login_ip_rate_limit(request: Request) -> None:
    """登录端点专用 IP 频控（较全站更严）。"""
    ip = _client_ip(request)
    limit = int(settings.login_rate_limit_per_minute)
    r = get_redis()
    if r is not None:
        _check_redis_bucket(f"ratelimit:login:ip:{ip}", limit=limit)
        return
    _check_memory_bucket(_ip_hits, f"login:{ip}", limit=limit, window=60.0)


def check_agent_rate_limit(user_id: int) -> None:
    limit = int(settings.agent_rate_limit_user_per_minute)
    r = get_redis()
    if r is not None:
        _check_redis_bucket(f"ratelimit:agent:user:{user_id}", limit=limit)
        return
    _check_memory_bucket(_user_hits, f"agent:{user_id}", limit=limit, window=60.0)
