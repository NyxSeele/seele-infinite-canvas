"""画布在线成员（Redis TTL + Pub/Sub）。"""

from __future__ import annotations

import json
import time
from typing import Any

from services.canvas_lock import publish_project_event
from services.canvas_ws_hub import schedule_broadcast
from services.redis_client import get_redis
from services.user_profile import enrich_presence_members

PRESENCE_TTL = 45
_MEMORY_PRESENCE: dict[str, dict[int, dict[str, Any]]] = {}


def _index_key(project_id: str) -> str:
    return f"canvas:presence:{project_id}:index"


def _user_key(project_id: str, user_id: int) -> str:
    return f"canvas:presence:{project_id}:{user_id}"


def _broadcast_presence(project_id: str, members: list[dict]) -> None:
    """Redis Pub/Sub + 本机 WebSocket 双通道，避免仅依赖订阅时序导致前端收不到。"""
    event = {"type": "presence_changed", "project_id": project_id, "members": members}
    publish_project_event(project_id, event)
    schedule_broadcast(project_id, event)


def touch_presence(
    project_id: str,
    user_id: int,
    username: str,
    *,
    is_editor: bool = False,
    avatar_url: str | None = None,
    display_name: str | None = None,
    email: str | None = None,
) -> list[dict]:
    payload = {
        "user_id": user_id,
        "username": username,
        "display_name": (display_name or "").strip() or username,
        "is_editor": bool(is_editor),
        "avatar_url": avatar_url or "",
        "email": (email or "").strip(),
        "since": time.time(),
    }
    r = get_redis()
    if r is None:
        bucket = _MEMORY_PRESENCE.setdefault(project_id, {})
        bucket[user_id] = payload
        members = list(bucket.values())
        _broadcast_presence(project_id, members)
        return members

    r.set(_user_key(project_id, user_id), json.dumps(payload), ex=PRESENCE_TTL)
    r.sadd(_index_key(project_id), str(user_id))
    members = list_presence(project_id)
    _broadcast_presence(project_id, members)
    return members


def leave_presence(project_id: str, user_id: int) -> list[dict]:
    r = get_redis()
    if r is None:
        bucket = _MEMORY_PRESENCE.get(project_id, {})
        bucket.pop(user_id, None)
        members = list(bucket.values())
        _broadcast_presence(project_id, members)
        return members

    r.delete(_user_key(project_id, user_id))
    r.srem(_index_key(project_id), str(user_id))
    members = list_presence(project_id)
    _broadcast_presence(project_id, members)
    return members


def list_presence(project_id: str) -> list[dict]:
    r = get_redis()
    if r is None:
        return list(_MEMORY_PRESENCE.get(project_id, {}).values())

    index = _index_key(project_id)
    user_ids = r.smembers(index) or set()
    members: list[dict] = []
    stale: list[str] = []
    for raw_uid in user_ids:
        uid = int(raw_uid) if str(raw_uid).isdigit() else raw_uid
        raw = r.get(_user_key(project_id, int(uid)))
        if not raw:
            stale.append(str(raw_uid))
            continue
        try:
            members.append(json.loads(raw))
        except (json.JSONDecodeError, TypeError):
            stale.append(str(raw_uid))
    if stale:
        r.srem(index, *stale)
    members.sort(key=lambda m: (not m.get("is_editor"), m.get("username") or ""))
    return enrich_presence_members(members)
