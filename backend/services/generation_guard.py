"""生成任务并发与配额前置检查。"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

from fastapi import HTTPException
from sqlalchemy.orm import Session

from core.config import settings
from models import Task, User
from services.generation_slots import acquire_slots
from services.rate_limit import check_user_rate_limit

# 与 tasks.py 中 _ACTIVE_TASK_STATUSES 保持一致
ACTIVE_TASK_STATUSES = ("pending", "queued", "running", "processing")
_ACTIVE_STATUSES = ACTIVE_TASK_STATUSES
_STALE_ACTIVE_SECONDS = 900  # 15 分钟未终态视为僵尸任务


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def release_stale_active_tasks(
    db: Session,
    user_id: int,
    *,
    max_age_seconds: int = _STALE_ACTIVE_SECONDS,
) -> int:
    """将长时间未终态的任务标为 failed，避免占用并发配额。"""
    cutoff = _utcnow() - timedelta(seconds=max_age_seconds)
    rows = (
        db.query(Task)
        .filter(
            Task.user_id == user_id,
            Task.status.in_(_ACTIVE_STATUSES),
            Task.created_at < cutoff,
        )
        .all()
    )
    for task in rows:
        task.status = "failed"
        task.error = "任务超时或已失效，请重新生成"
        task.result = None
    if rows:
        db.flush()
    return len(rows)


async def reconcile_active_tasks_from_comfyui(db: Session, user_id: int) -> int:
    """将 DB 中仍标记为进行中的 ComfyUI 任务与队列/历史对齐。"""
    from comfyui import client as comfyui

    rows = (
        db.query(Task)
        .filter(
            Task.user_id == user_id,
            Task.status.in_(_ACTIVE_STATUSES),
            Task.comfyui_prompt_id.isnot(None),
        )
        .order_by(Task.created_at.desc())
        .limit(20)
        .all()
    )
    updated = 0
    for task in rows:
        try:
            exec_info = await comfyui.get_prompt_execution_status(task.comfyui_prompt_id)
        except Exception:
            continue
        api_status = exec_info.get("status") or task.status
        if api_status == "completed":
            result = exec_info.get("result")
            if result:
                task.status = "completed"
                task.result = result
                task.error = None
                updated += 1
            elif (_utcnow() - task.created_at).total_seconds() > 600:
                task.status = "failed"
                task.error = "ComfyUI 已完成但未返回结果"
                updated += 1
        elif api_status == "failed":
            task.status = "failed"
            task.error = (exec_info.get("error") or "生成失败")[:2000]
            updated += 1
        elif api_status in ("pending", "running", "queued"):
            if task.status != api_status:
                task.status = api_status
                updated += 1
        elif (_utcnow() - task.created_at).total_seconds() > 600:
            task.status = "failed"
            task.error = "ComfyUI 中未找到该任务，可能已过期"
            updated += 1
    if updated:
        db.flush()
    return updated


def check_concurrent_generations(
    db: Session,
    user: User,
    *,
    slots_needed: int = 1,
    team_id: str | None = None,
) -> None:
    if team_id:
        from services.team_service import get_member_role

        if not get_member_role(db, team_id, user.id):
            raise HTTPException(status_code=403, detail="无权在该团队下提交生成任务")
    check_user_rate_limit(user.id)
    limit = int(settings.generation_max_concurrent)
    release_stale_active_tasks(db, user.id)

    needed = max(1, int(slots_needed or 1))
    if limit > 0:
        active = (
            db.query(Task.id)
            .filter(Task.user_id == user.id, Task.status.in_(_ACTIVE_STATUSES))
            .count()
        )
        if active + needed > limit:
            raise HTTPException(
                status_code=429,
                detail=f"同时进行的生成任务过多（上限 {limit}），请等待当前任务完成",
            )

    acquire_slots(user.id, team_id=team_id, slots_needed=needed)
