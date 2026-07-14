"""生成任务并发与配额前置检查。"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

from fastapi import HTTPException
from sqlalchemy.orm import Session

from core.config import settings
from models import Task, User
from services.task_state import SEEDANCE_PENDING_IDS, reload_task_if_active, should_refund_video_quota
from services.video_postprocess import schedule_video_postprocess
from services.generation_slots import (
    acquire_slots,
    release_slot_for_task,
    release_slots,
    set_slot_counts,
)
from services.quota_service import refund_quota
from services.rate_limit import check_user_rate_limit

# 与 tasks.py 中 _ACTIVE_TASK_STATUSES 保持一致
ACTIVE_TASK_STATUSES = ("pending", "queued", "running", "processing")
_ACTIVE_STATUSES = ACTIVE_TASK_STATUSES
_TERMINAL_STATUSES = frozenset({"completed", "failed", "cancelled", "timeout"})
_STALE_ACTIVE_SECONDS = 900  # 15 分钟未终态视为僵尸任务
_MEDIA_QUOTA_REFUND_TYPES = frozenset({"image", "video", "video_enhance", "video_lut"})


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def count_active_tasks(
    db: Session,
    user_id: int,
    *,
    team_id: str | None = None,
) -> tuple[int, int]:
    user_active = (
        db.query(Task.id)
        .filter(Task.user_id == user_id, Task.status.in_(_ACTIVE_STATUSES))
        .count()
    )
    team_active = 0
    if team_id:
        team_active = (
            db.query(Task.id)
            .filter(Task.team_id == team_id, Task.status.in_(_ACTIVE_STATUSES))
            .count()
        )
    return user_active, team_active


def sync_slots_from_db(
    db: Session,
    user_id: int,
    *,
    team_id: str | None = None,
) -> None:
    """用 DB 活跃任务数校正 Redis，修复失败/异常未 release 的泄漏。"""
    user_active, team_active = count_active_tasks(db, user_id, team_id=team_id)
    set_slot_counts(user_id, user_active, team_id=team_id, team_active=team_active)


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
        release_slot_for_task(task)
        if task.task_type in _MEDIA_QUOTA_REFUND_TYPES and task.user_id:
            quota_kind = "image" if task.task_type == "image" else "video"
            if should_refund_video_quota(task):
                refund_quota(db, task.user_id, quota_kind, 1)
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
        cid = (task.comfyui_prompt_id or "").strip()
        if (
            cid in SEEDANCE_PENDING_IDS
            or cid.startswith("seedance:")
            or task.task_type == "video_lut"
        ):
            continue
        from services import mock_generation

        if cid == mock_generation.MOCK_PROMPT_ID:
            continue
        old_status = task.status
        try:
            exec_info = await comfyui.get_prompt_execution_status(
                task.comfyui_prompt_id,
                node_url=task.comfyui_node_url,
            )
        except Exception:
            continue
        task = reload_task_if_active(db, task)
        if task is None:
            continue
        api_status = exec_info.get("status") or task.status
        if api_status == "completed":
            result = exec_info.get("result")
            if result:
                if old_status in _ACTIVE_STATUSES:
                    release_slots(task.user_id, team_id=task.team_id)
                task.status = "completed"
                task.result = result
                task.error = None
                if task.task_type == "video":
                    schedule_video_postprocess(task)
                from services.gpu_pool import release_gpu_node

                release_gpu_node(task.comfyui_node_url)
                updated += 1
            elif (_utcnow() - task.created_at).total_seconds() > 600:
                if old_status in _ACTIVE_STATUSES:
                    release_slots(task.user_id, team_id=task.team_id)
                task.status = "failed"
                task.error = "ComfyUI 已完成但未返回结果"
                updated += 1
        elif api_status == "failed":
            if old_status in _ACTIVE_STATUSES:
                release_slots(task.user_id, team_id=task.team_id)
            task.status = "failed"
            task.error = (exec_info.get("error") or "生成失败")[:2000]
            from services.gpu_pool import release_gpu_node

            release_gpu_node(task.comfyui_node_url)
            updated += 1
        elif api_status in ("pending", "running", "queued"):
            if task.status != api_status:
                task.status = api_status
                updated += 1
        elif (_utcnow() - task.created_at).total_seconds() > 600:
            if old_status in _ACTIVE_STATUSES:
                release_slots(task.user_id, team_id=task.team_id)
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
    sync_slots_from_db(db, user.id, team_id=team_id)

    needed = max(1, int(slots_needed or 1))
    if limit > 0:
        active, _team_active = count_active_tasks(db, user.id, team_id=team_id)
        if active + needed > limit:
            raise HTTPException(
                status_code=429,
                detail=f"同时进行的生成任务过多（上限 {limit}），请等待当前任务完成",
            )

    acquire_slots(user.id, team_id=team_id, slots_needed=needed)
