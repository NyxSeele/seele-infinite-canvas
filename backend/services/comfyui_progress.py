"""ComfyUI 执行进度缓存（由 WebSocket 代理写入，HTTP 轮询读取）。"""

from __future__ import annotations

import time
from threading import Lock

_lock = Lock()
_by_prompt: dict[str, dict] = {}
_active_by_client: dict[str, str] = {}


def set_active_prompt(client_id: str | None, prompt_id: str | None) -> None:
    if not client_id or not prompt_id:
        return
    with _lock:
        _active_by_client[str(client_id)] = str(prompt_id)


def resolve_prompt_id(client_id: str | None, data: dict | None) -> str | None:
    if not data:
        return None
    pid = data.get("prompt_id")
    if pid:
        return str(pid)
    if client_id:
        with _lock:
            return _active_by_client.get(str(client_id))
    return None


def record_progress(
    prompt_id: str,
    value: int,
    max_val: int,
    *,
    node: str | None = None,
) -> None:
    if not prompt_id:
        return
    try:
        v = int(value)
        m = int(max_val)
    except (TypeError, ValueError):
        return
    if m > 0:
        progress = min(100, max(0, round(v / m * 100)))
    else:
        progress = 0
    with _lock:
        _by_prompt[str(prompt_id)] = {
            "value": v,
            "max": m,
            "progress": progress,
            "node": node,
            "stage": node or "sampling",
            "updated_at": time.time(),
        }


def get_progress(prompt_id: str) -> dict | None:
    if not prompt_id:
        return None
    with _lock:
        row = _by_prompt.get(str(prompt_id))
        return dict(row) if row else None


def clear_progress(prompt_id: str) -> None:
    if not prompt_id:
        return
    with _lock:
        _by_prompt.pop(str(prompt_id), None)
