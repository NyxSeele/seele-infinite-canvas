"""画布编辑顶号锁（Redis）。"""

from __future__ import annotations

import json
import time
import uuid
from typing import Any

from core.config import settings
from services.redis_client import get_redis

LOCK_PREFIX = "canvas:lock:"
EVENT_PREFIX = "canvas:events:"
EDIT_REQUEST_PREFIX = "canvas:edit_request:"
EDIT_REQUEST_TTL_SECONDS = 30

# 无 Redis 时单进程内存锁（顶号仍可用，Pub/Sub 不可用）
_MEMORY_LOCKS: dict[str, dict[str, Any]] = {}
_MEMORY_EDIT_REQUESTS: dict[str, dict[str, Any]] = {}


def _lock_key(project_id: str) -> str:
    return f"{LOCK_PREFIX}{project_id}"


def _event_channel(project_id: str) -> str:
    return f"{EVENT_PREFIX}{project_id}"


def acquire_lock(
    project_id: str,
    user_id: int,
    username: str,
    *,
    display_name: str | None = None,
) -> dict[str, Any]:
    """抢占编辑锁；若顶掉他人则返回 kicked 信息。"""
    r = get_redis()
    ttl = int(settings.canvas_lock_ttl_seconds)
    session_id = str(uuid.uuid4())
    payload = {
        "user_id": user_id,
        "username": username,
        "display_name": (display_name or "").strip() or username,
        "session_id": session_id,
        "since": time.time(),
    }
    kicked: dict | None = None
    key = _lock_key(project_id)

    if r is None:
        prev = _MEMORY_LOCKS.get(project_id)
        if prev and int(prev.get("user_id", -1)) != user_id:
            kicked = {
                "user_id": prev.get("user_id"),
                "username": prev.get("username"),
                "session_id": prev.get("session_id"),
            }
        _MEMORY_LOCKS[project_id] = payload
        return {
            "editor": True,
            "session_id": session_id,
            "kicked": kicked,
            "lock": payload,
        }
    prev_raw = r.get(key)
    if prev_raw:
        try:
            prev = json.loads(prev_raw)
            if int(prev.get("user_id", -1)) != user_id:
                kicked = {
                    "user_id": prev.get("user_id"),
                    "username": prev.get("username"),
                    "session_id": prev.get("session_id"),
                }
        except (json.JSONDecodeError, TypeError, ValueError):
            pass

    r.set(key, json.dumps(payload), ex=ttl)
    if kicked:
        r.publish(
            _event_channel(project_id),
            json.dumps({"type": "session_kicked", "kicked": kicked, "by": payload}),
        )
    return {
        "editor": True,
        "session_id": session_id,
        "kicked": kicked,
        "lock": payload,
    }


def heartbeat_lock(project_id: str, user_id: int, session_id: str) -> bool:
    r = get_redis()
    if r is None:
        lock = _MEMORY_LOCKS.get(project_id)
        if not lock:
            return False
        if int(lock.get("user_id", -1)) != user_id or lock.get("session_id") != session_id:
            return False
        lock["since"] = time.time()
        _MEMORY_LOCKS[project_id] = lock
        return True
    key = _lock_key(project_id)
    raw = r.get(key)
    if not raw:
        return False
    try:
        data = json.loads(raw)
    except (json.JSONDecodeError, TypeError):
        return False
    if int(data.get("user_id", -1)) != user_id:
        return False
    if data.get("session_id") != session_id:
        return False
    data["since"] = time.time()
    r.set(key, json.dumps(data), ex=int(settings.canvas_lock_ttl_seconds))
    return True


def release_lock(project_id: str, user_id: int, session_id: str) -> None:
    r = get_redis()
    if r is None:
        lock = _MEMORY_LOCKS.get(project_id)
        if lock and int(lock.get("user_id", -1)) == user_id and lock.get("session_id") == session_id:
            released_by = {
                "user_id": lock.get("user_id"),
                "username": lock.get("username"),
                "display_name": lock.get("display_name"),
            }
            _MEMORY_LOCKS.pop(project_id, None)
            publish_project_event(
                project_id,
                {"type": "session_released", "released_by": released_by},
            )
        return
    key = _lock_key(project_id)
    raw = r.get(key)
    if not raw:
        return
    try:
        data = json.loads(raw)
    except (json.JSONDecodeError, TypeError):
        r.delete(key)
        return
    if int(data.get("user_id", -1)) == user_id and data.get("session_id") == session_id:
        released_by = {
            "user_id": data.get("user_id"),
            "username": data.get("username"),
            "display_name": data.get("display_name"),
        }
        r.delete(key)
        publish_project_event(
            project_id,
            {"type": "session_released", "released_by": released_by},
        )


def get_lock(project_id: str) -> dict | None:
    r = get_redis()
    if r is None:
        return _MEMORY_LOCKS.get(project_id)
    raw = r.get(_lock_key(project_id))
    if not raw:
        return None
    try:
        return json.loads(raw)
    except (json.JSONDecodeError, TypeError):
        return None


def is_editor(project_id: str, user_id: int, session_id: str | None) -> bool:
    lock = get_lock(project_id)
    if not lock:
        return True
    if int(lock.get("user_id", -1)) != user_id:
        return False
    if session_id and lock.get("session_id") != session_id:
        return False
    return True


def event_channel(project_id: str) -> str:
    return _event_channel(project_id)


def publish_project_event(project_id: str, payload: dict[str, Any]) -> None:
    from services.canvas_ws_hub import schedule_broadcast

    r = get_redis()
    if r is None:
        schedule_broadcast(project_id, payload)
        return
    try:
        r.publish(_event_channel(project_id), json.dumps(payload))
    except Exception:
        pass


def publish_canvas_updated(
    project_id: str,
    *,
    version: int,
    user_id: int,
    username: str,
    display_name: str | None = None,
    name: str | None = None,
) -> None:
    """保存成功后通知只读协作者刷新。"""
    publish_project_event(
        project_id,
        {
            "type": "canvas_updated",
            "project_id": project_id,
            "version": version,
            "by": {
                "user_id": user_id,
                "username": username,
                "display_name": (display_name or "").strip() or username,
            },
            "name": name,
        },
    )


def _edit_request_key(project_id: str) -> str:
    return f"{EDIT_REQUEST_PREFIX}{project_id}"


def get_pending_edit_request(project_id: str) -> dict[str, Any] | None:
    r = get_redis()
    if r is None:
        req = _MEMORY_EDIT_REQUESTS.get(project_id)
        if not req:
            return None
        if float(req.get("expires_at", 0)) < time.time():
            _MEMORY_EDIT_REQUESTS.pop(project_id, None)
            return None
        return req
    raw = r.get(_edit_request_key(project_id))
    if not raw:
        return None
    try:
        return json.loads(raw)
    except (json.JSONDecodeError, TypeError):
        return None


def create_edit_request(
    project_id: str,
    *,
    requester_id: int,
    requester_username: str,
    requester_display_name: str | None = None,
) -> dict[str, Any]:
    lock = get_lock(project_id)
    if not lock:
        raise ValueError("当前无人持有编辑锁，无需请求")
    if int(lock.get("user_id", -1)) == int(requester_id):
        raise ValueError("你已是编辑者")
    existing = get_pending_edit_request(project_id)
    if existing and int(existing.get("requester", {}).get("user_id", -1)) == int(requester_id):
        return existing
    if existing:
        raise ValueError("已有他人正在等待编辑者响应")

    request_id = str(uuid.uuid4())
    payload = {
        "request_id": request_id,
        "requester": {
            "user_id": requester_id,
            "username": requester_username,
            "display_name": (requester_display_name or "").strip() or requester_username,
        },
        "expires_at": time.time() + EDIT_REQUEST_TTL_SECONDS,
    }
    r = get_redis()
    if r is None:
        _MEMORY_EDIT_REQUESTS[project_id] = payload
    else:
        r.set(
            _edit_request_key(project_id),
            json.dumps(payload),
            ex=EDIT_REQUEST_TTL_SECONDS,
        )
    publish_project_event(
        project_id,
        {
            "type": "edit_request",
            "project_id": project_id,
            "request_id": request_id,
            "requester": payload["requester"],
            "expires_at": payload["expires_at"],
        },
    )
    return payload


def _clear_edit_request(project_id: str) -> None:
    r = get_redis()
    if r is None:
        _MEMORY_EDIT_REQUESTS.pop(project_id, None)
    else:
        r.delete(_edit_request_key(project_id))


def transfer_lock_to_user(
    project_id: str,
    from_user_id: int,
    from_session_id: str,
    *,
    to_user_id: int,
    to_username: str,
    to_display_name: str | None = None,
) -> dict[str, Any]:
    """编辑者同意后把锁直接转给请求者（避免 session_released 抢锁竞态）。"""
    r = get_redis()
    ttl = int(settings.canvas_lock_ttl_seconds)
    new_session_id = str(uuid.uuid4())
    new_payload = {
        "user_id": to_user_id,
        "username": to_username,
        "display_name": (to_display_name or "").strip() or to_username,
        "session_id": new_session_id,
        "since": time.time(),
    }
    key = _lock_key(project_id)

    if r is None:
        lock = _MEMORY_LOCKS.get(project_id)
        if not lock:
            raise ValueError("编辑锁不存在")
        if int(lock.get("user_id", -1)) != int(from_user_id):
            raise ValueError("你不是当前编辑者")
        if lock.get("session_id") != from_session_id:
            raise ValueError("会话已失效")
        kicked = {
            "user_id": lock.get("user_id"),
            "username": lock.get("username"),
            "session_id": lock.get("session_id"),
        }
        _MEMORY_LOCKS[project_id] = new_payload
    else:
        raw = r.get(key)
        if not raw:
            raise ValueError("编辑锁不存在")
        try:
            lock = json.loads(raw)
        except (json.JSONDecodeError, TypeError):
            raise ValueError("编辑锁数据损坏")
        if int(lock.get("user_id", -1)) != int(from_user_id):
            raise ValueError("你不是当前编辑者")
        if lock.get("session_id") != from_session_id:
            raise ValueError("会话已失效")
        kicked = {
            "user_id": lock.get("user_id"),
            "username": lock.get("username"),
            "session_id": lock.get("session_id"),
        }
        r.set(key, json.dumps(new_payload), ex=ttl)

    publish_project_event(
        project_id,
        {
            "type": "session_kicked",
            "kicked": kicked,
            "by": new_payload,
        },
    )
    return {
        "session_id": new_session_id,
        "lock": new_payload,
    }


def respond_edit_request(
    project_id: str,
    *,
    editor_user_id: int,
    editor_session_id: str,
    request_id: str,
    approved: bool,
) -> dict[str, Any]:
    pending = get_pending_edit_request(project_id)
    if not pending or pending.get("request_id") != request_id:
        raise ValueError("编辑请求不存在或已过期")
    requester = pending.get("requester") or {}
    lock = get_lock(project_id)
    if not lock or int(lock.get("user_id", -1)) != int(editor_user_id):
        raise ValueError("你不是当前编辑者")
    if lock.get("session_id") != editor_session_id:
        raise ValueError("会话已失效")

    _clear_edit_request(project_id)

    if not approved:
        publish_project_event(
            project_id,
            {
                "type": "edit_request_response",
                "project_id": project_id,
                "status": "denied",
                "request_id": request_id,
                "requester": requester,
            },
        )
        return {"status": "denied"}

    transfer = transfer_lock_to_user(
        project_id,
        editor_user_id,
        editor_session_id,
        to_user_id=int(requester.get("user_id")),
        to_username=str(requester.get("username") or ""),
        to_display_name=requester.get("display_name"),
    )
    publish_project_event(
        project_id,
        {
            "type": "edit_request_response",
            "project_id": project_id,
            "status": "approved",
            "request_id": request_id,
            "requester": requester,
            "session_id": transfer["session_id"],
            "lock": transfer["lock"],
        },
    )
    return {"status": "approved", **transfer}
