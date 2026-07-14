"""任务可写性与配额执行态判定（供 worker / guard / refund 共用）。"""

from __future__ import annotations

from sqlalchemy.orm import Session

from models import Task

_WRITABLE_TASK_STATUSES = frozenset({"pending", "queued", "running", "processing"})
ACTIVE_TASK_STATUSES = _WRITABLE_TASK_STATUSES
_TERMINAL_TASK_STATUSES = frozenset({"completed", "failed", "cancelled", "timeout"})
SEEDANCE_PENDING_IDS = frozenset({"seedance", "seedance:pending"})


def task_is_writable(task: Task | None) -> bool:
    return task is not None and task.status in _WRITABLE_TASK_STATUSES


def task_is_active(task: Task | None) -> bool:
    return task_is_writable(task)


def task_is_terminal(task: Task | None) -> bool:
    return task is not None and task.status in _TERMINAL_TASK_STATUSES


def reload_task_if_active(db: Session, task: Task | None) -> Task | None:
    """长异步操作后刷新行；若任务已终态则返回 None，避免覆盖「被新任务取代」等状态。"""
    if task is None:
        return None
    db.expire(task)
    refreshed = db.get(Task, task.id)
    if not task_is_writable(refreshed):
        return None
    return refreshed


def comfy_id_counts_as_executed(task: Task) -> bool:
    """任务是否已拿到真实外部执行 id（Seedance pending 占位不算）。"""
    cid = (task.comfyui_prompt_id or "").strip()
    if not cid:
        return False
    if task.task_type == "video" and cid in SEEDANCE_PENDING_IDS:
        return False
    return True


def is_comfy_cancellable_prompt_id(comfyui_prompt_id: str | None) -> bool:
    """仅真实 Comfy prompt id 才应调用 Comfy cancel API。"""
    cid = (comfyui_prompt_id or "").strip()
    if not cid:
        return False
    if cid in SEEDANCE_PENDING_IDS or cid.startswith("seedance:"):
        return False
    from services import mock_generation

    if cid == mock_generation.MOCK_PROMPT_ID:
        return False
    return True


def should_refund_video_quota(task: Task) -> bool:
    if task.task_type == "video_lut":
        return not (task.result and str(task.result).strip())
    if task.task_type == "image":
        return not task.comfyui_prompt_id
    return not comfy_id_counts_as_executed(task)
