"""GET /api/teams/mine 短缓存，防止前端异常时打爆数据库。"""

from __future__ import annotations

from threading import Lock
from time import monotonic

_lock = Lock()
_cache: dict[int, tuple[float, object]] = {}
_last_db_at: dict[int, float] = {}

TTL_SECONDS = 60.0
MIN_DB_INTERVAL_SECONDS = 5.0


def get_fresh(user_id: int) -> object | None:
    with _lock:
        row = _cache.get(user_id)
        if not row:
            return None
        ts, payload = row
        if monotonic() - ts > TTL_SECONDS:
            return None
        return payload


def get_stale(user_id: int) -> object | None:
    with _lock:
        row = _cache.get(user_id)
        return row[1] if row else None


def allow_db_hit(user_id: int) -> bool:
    with _lock:
        now = monotonic()
        last = _last_db_at.get(user_id, 0.0)
        if now - last < MIN_DB_INTERVAL_SECONDS:
            return False
        _last_db_at[user_id] = now
        return True


def store(user_id: int, payload: object) -> None:
    with _lock:
        _cache[user_id] = (monotonic(), payload)


def invalidate_user(user_id: int) -> None:
    with _lock:
        _cache.pop(user_id, None)
        _last_db_at.pop(user_id, None)


def invalidate_users(*user_ids: int) -> None:
    for uid in user_ids:
        invalidate_user(uid)
