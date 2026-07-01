"""画布 WebSocket 连接池：无 Redis 时广播 presence / 事件。"""

from __future__ import annotations

import asyncio
import json
from typing import Any

from fastapi import WebSocket

_CONNECTIONS: dict[str, set[WebSocket]] = {}


def register(project_id: str, websocket: WebSocket) -> None:
    bucket = _CONNECTIONS.setdefault(project_id, set())
    bucket.add(websocket)


def unregister(project_id: str, websocket: WebSocket) -> None:
    bucket = _CONNECTIONS.get(project_id)
    if not bucket:
        return
    bucket.discard(websocket)
    if not bucket:
        _CONNECTIONS.pop(project_id, None)


async def broadcast_json(project_id: str, payload: dict[str, Any]) -> None:
    bucket = _CONNECTIONS.get(project_id)
    if not bucket:
        return
    dead: list[WebSocket] = []
    text = json.dumps(payload, ensure_ascii=False)
    for ws in list(bucket):
        try:
            await ws.send_text(text)
        except Exception:
            dead.append(ws)
    for ws in dead:
        bucket.discard(ws)


def schedule_broadcast(project_id: str, payload: dict[str, Any]) -> None:
    """从同步上下文调度广播（presence 更新等）。"""
    try:
        loop = asyncio.get_running_loop()
    except RuntimeError:
        return
    loop.create_task(broadcast_json(project_id, payload))
