"""Redis 生成任务并发槽位（用户 + 团队）。"""

from __future__ import annotations

from fastapi import HTTPException

from core.config import settings
from services.redis_client import get_redis

_USER_KEY = "gen:active:user:{user_id}"
_TEAM_KEY = "gen:active:team:{team_id}"
_SLOT_TTL = 600


def _user_key(user_id: int) -> str:
    return _USER_KEY.format(user_id=user_id)


def _team_key(team_id: str) -> str:
    return _TEAM_KEY.format(team_id=team_id)


def acquire_slots(
    user_id: int,
    *,
    team_id: str | None = None,
    slots_needed: int = 1,
) -> None:
    needed = max(1, int(slots_needed or 1))
    user_limit = int(settings.generation_max_concurrent)
    team_limit = int(settings.generation_max_concurrent_team)
    r = get_redis()
    if r is None:
        return

    pipe = r.pipeline()
    uk = _user_key(user_id)
    pipe.get(uk)
    if team_id:
        pipe.get(_team_key(team_id))
    results = pipe.execute()
    user_active = int(results[0] or 0)
    team_active = int(results[1] or 0) if team_id else 0

    if user_limit > 0 and user_active + needed > user_limit:
        raise HTTPException(
            status_code=429,
            detail=f"同时进行的生成任务过多（个人上限 {user_limit}），请稍后再试",
        )
    if team_id and team_limit > 0 and team_active + needed > team_limit:
        raise HTTPException(
            status_code=429,
            detail=f"团队并发生成已达上限（{team_limit}），请稍后再试",
        )

    pipe = r.pipeline()
    pipe.incrby(uk, needed)
    pipe.expire(uk, _SLOT_TTL)
    if team_id:
        tk = _team_key(team_id)
        pipe.incrby(tk, needed)
        pipe.expire(tk, _SLOT_TTL)
    pipe.execute()


def release_slots(
    user_id: int | None,
    *,
    team_id: str | None = None,
    slots: int = 1,
) -> None:
    if user_id is None:
        return
    r = get_redis()
    if r is None:
        return
    n = max(1, int(slots or 1))
    uk = _user_key(user_id)
    pipe = r.pipeline()
    pipe.decrby(uk, n)
    if team_id:
        pipe.decrby(_team_key(team_id), n)
    results = pipe.execute()
    if int(results[0] or 0) < 0:
        r.set(uk, 0, ex=_SLOT_TTL)
    if team_id and len(results) > 1 and int(results[1] or 0) < 0:
        r.set(_team_key(team_id), 0, ex=_SLOT_TTL)
