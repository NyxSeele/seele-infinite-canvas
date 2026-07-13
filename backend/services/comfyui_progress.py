"""ComfyUI 执行进度缓存（由 WebSocket 代理写入，HTTP 轮询读取）。

ComfyUI 的 progress 事件按「当前节点」上报 value/max。Wan 等双 KSampler
工作流会在第二段采样时从 0 重新计数，若直接 v/max*100 会在 0/50/100 间回跳。
这里按采样阶段做等分映射，并保持单调递增（完成前封顶 95）。
"""

from __future__ import annotations

import time
from threading import Lock

_lock = Lock()
_by_prompt: dict[str, dict] = {}
_active_by_client: dict[str, str] = {}

# 运行中最高显示到 95，100 留给任务真正完成
_RUNNING_CAP = 95


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


def set_expected_stages(prompt_id: str | None, stages: int) -> None:
    """提交工作流后声明采样阶段数（如 Wan 双 KSampler = 2）。"""
    if not prompt_id:
        return
    try:
        n = max(1, int(stages))
    except (TypeError, ValueError):
        return
    pid = str(prompt_id)
    with _lock:
        row = _by_prompt.get(pid) or {}
        row["expected_stages"] = n
        row.setdefault("progress", 0)
        row.setdefault("stage_index", 0)
        row.setdefault("updated_at", time.time())
        _by_prompt[pid] = row


def _guess_stages_from_node(node: str | None) -> int | None:
    if not node:
        return None
    key = str(node).lower()
    # Wan 双段 / LTX2 SamplerCustomAdvanced 节点
    if any(s in key for s in ("sample_h", "sample_l", "sampler_h", "sampler_l")):
        return 2
    if key in ("113", "119", "115", "114"):
        return 2
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
    if m <= 0:
        return
    frac = min(1.0, max(0.0, v / m))
    pid = str(prompt_id)
    node_key = str(node) if node is not None else None

    with _lock:
        row = _by_prompt.get(pid) or {
            "progress": 0,
            "stage_index": 0,
            "expected_stages": 1,
            "last_frac": 0.0,
            "node": None,
        }
        prev_node = row.get("node")
        last_frac = float(row.get("last_frac") or 0.0)
        stage_index = int(row.get("stage_index") or 0)
        expected = max(1, int(row.get("expected_stages") or 1))

        guessed = _guess_stages_from_node(node_key) or _guess_stages_from_node(prev_node)
        if guessed:
            expected = max(expected, guessed)

        new_stage = False
        if node_key and prev_node and node_key != prev_node:
            new_stage = True
        elif last_frac >= 0.8 and frac <= 0.25 and int(row.get("progress") or 0) >= 8:
            # 无 node 字段时：明显回绕也视为进入下一阶段
            new_stage = True

        if new_stage:
            stage_index += 1
            expected = max(expected, stage_index + 1)

        overall = ((stage_index + frac) / expected) * _RUNNING_CAP
        # 单调：避免轮询/乱序事件把进度打回去
        overall = max(float(row.get("progress") or 0), overall)
        overall = min(float(_RUNNING_CAP), overall)

        _by_prompt[pid] = {
            "value": v,
            "max": m,
            "progress": int(round(overall)),
            "node": node_key or prev_node,
            "stage": node_key or row.get("stage") or "sampling",
            "stage_index": stage_index,
            "expected_stages": expected,
            "last_frac": frac,
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
