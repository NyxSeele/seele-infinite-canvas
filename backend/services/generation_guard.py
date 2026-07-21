"""生成任务并发与配额前置检查。"""

from __future__ import annotations

import logging
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

logger = logging.getLogger(__name__)

# 与 tasks.py 中 _ACTIVE_TASK_STATUSES 保持一致
ACTIVE_TASK_STATUSES = ("pending", "queued", "running", "processing")
_ACTIVE_STATUSES = ACTIVE_TASK_STATUSES
_TERMINAL_STATUSES = frozenset({"completed", "failed", "cancelled", "timeout"})
# 仅作「开始考虑回收」的年龄门槛；真正超时前必须确认后端未在跑
_STALE_ACTIVE_SECONDS = 900
_MEDIA_QUOTA_REFUND_TYPES = frozenset({"image", "video", "video_enhance", "video_lut"})
_BACKEND_BUSY = frozenset({"pending", "queued", "running", "processing"})


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


def _is_comfy_backed_task(task: Task) -> bool:
    cid = (task.comfyui_prompt_id or "").strip()
    if not cid:
        return False
    if cid in SEEDANCE_PENDING_IDS or cid.startswith("seedance:"):
        return False
    if task.task_type == "video_lut":
        return False
    from services import mock_generation

    if cid == mock_generation.MOCK_PROMPT_ID:
        return False
    return True


def _fail_stale_task(db: Session, task: Task, *, error: str) -> None:
    release_slot_for_task(task)
    if task.task_type in _MEDIA_QUOTA_REFUND_TYPES and task.user_id:
        quota_kind = "image" if task.task_type == "image" else "video"
        if should_refund_video_quota(task):
            refund_quota(db, task.user_id, quota_kind, 1)
    task.status = "failed"
    task.error = error
    task.result = None


def _complete_recovered_task(task: Task, *, result: str) -> None:
    if task.status in _ACTIVE_STATUSES:
        release_slots(task.user_id, team_id=task.team_id)
    task.status = "completed"
    task.result = result
    task.error = None
    if task.task_type == "video":
        schedule_video_postprocess(task)
    from services.gpu_pool import release_gpu_node

    release_gpu_node(task.comfyui_node_url)


async def release_stale_active_tasks(
    db: Session,
    user_id: int,
    *,
    max_age_seconds: int = _STALE_ACTIVE_SECONDS,
) -> int:
    """
    回收长时间未终态任务。

    规则：凡已提交到 Comfy 的任务，超时前必须探测后端；
    仍在 queue/running 或近期有进度 → 绝不误杀。
    后端不可达 → 保留，等待下次核对。
    """
    from comfyui import client as comfyui

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
    killed = 0
    for task in rows:
        if not _is_comfy_backed_task(task):
            # 未进 Comfy / 非 Comfy 后端：仅按年龄回收（从未占用 GPU 队列）
            _fail_stale_task(db, task, error="任务超时或已失效，请重新生成")
            killed += 1
            continue

        cid = (task.comfyui_prompt_id or "").strip()
        try:
            live = await comfyui.probe_comfy_prompt_liveness(
                cid, node_url=task.comfyui_node_url
            )
        except Exception:
            logger.exception(
                "stale probe failed task_id=%s prompt_id=%s", task.id, cid
            )
            continue

        state = live.get("state")
        if state == "busy":
            logger.info(
                "skip stale kill: backend still busy task_id=%s prompt_id=%s status=%s",
                task.id,
                cid,
                live.get("status"),
            )
            continue
        if state == "unreachable":
            logger.info(
                "skip stale kill: backend unreachable task_id=%s prompt_id=%s",
                task.id,
                cid,
            )
            continue

        # idle：后端已确认不在跑
        api_status = live.get("status")
        result = live.get("result")
        if api_status == "completed" and result:
            _complete_recovered_task(task, result=result)
            killed += 1
            continue
        if api_status == "failed":
            release_slot_for_task(task)
            if task.task_type in _MEDIA_QUOTA_REFUND_TYPES and task.user_id:
                if should_refund_video_quota(task):
                    refund_quota(
                        db,
                        task.user_id,
                        "image" if task.task_type == "image" else "video",
                        1,
                    )
            task.status = "failed"
            task.error = (live.get("error") or "生成失败")[:2000]
            task.result = None
            from services.gpu_pool import release_gpu_node

            release_gpu_node(task.comfyui_node_url)
            killed += 1
            continue

        _fail_stale_task(
            db,
            task,
            error=(live.get("error") or "任务超时或已失效，请重新生成")[:2000],
        )
        killed += 1

    if killed:
        db.flush()
    return killed


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
                # completed 但无产物：再做一次 liveness，确认确已不在跑
                live = await comfyui.probe_comfy_prompt_liveness(
                    cid, node_url=task.comfyui_node_url
                )
                if live.get("state") != "idle":
                    continue
                if old_status in _ACTIVE_STATUSES:
                    release_slots(task.user_id, team_id=task.team_id)
                task.status = "failed"
                task.error = live.get("error") or "ComfyUI 已完成但未返回结果"
                updated += 1
        elif api_status == "failed":
            if old_status in _ACTIVE_STATUSES:
                release_slots(task.user_id, team_id=task.team_id)
            task.status = "failed"
            task.error = (exec_info.get("error") or "生成失败")[:2000]
            from services.gpu_pool import release_gpu_node

            release_gpu_node(task.comfyui_node_url)
            updated += 1
        elif api_status in _BACKEND_BUSY:
            if task.status != api_status and api_status in _ACTIVE_STATUSES:
                task.status = api_status
                updated += 1
        elif (_utcnow() - task.created_at).total_seconds() > 600:
            # 未知状态：必须用 liveness 确认后端已空闲才允许超时
            live = await comfyui.probe_comfy_prompt_liveness(
                cid, node_url=task.comfyui_node_url
            )
            if live.get("state") != "idle":
                continue
            if live.get("status") == "completed" and live.get("result"):
                _complete_recovered_task(task, result=live["result"])
                updated += 1
                continue
            if old_status in _ACTIVE_STATUSES:
                release_slots(task.user_id, team_id=task.team_id)
            task.status = "failed"
            task.error = (
                live.get("error") or "ComfyUI 中未找到该任务，可能已过期"
            )[:2000]
            updated += 1
    if updated:
        db.flush()
    return updated


async def check_concurrent_generations(
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
    await release_stale_active_tasks(db, user.id)
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
