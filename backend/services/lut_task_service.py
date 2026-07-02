"""视频 LUT 任务队列与执行。"""

from __future__ import annotations

import asyncio
import logging
import shutil
import uuid
from pathlib import Path

from fastapi import HTTPException
from sqlalchemy.orm import Session

from core.config import settings
from db.session import SessionLocal
from models import Task, User
from services import mock_generation, tasks_cache
from services.generation_guard import check_concurrent_generations
from services.quota_service import QuotaExceededError, check_and_consume, create_task_record
from services.video_lut_service import (
    apply_lut_to_video_file,
    new_lut_output_path,
    resolve_lut_file_path,
)

logger = logging.getLogger(__name__)


def _release_task_slots(task: Task) -> None:
    from services.generation_slots import release_slots

    if task.user_id:
        release_slots(task.user_id, team_id=task.team_id)


async def queue_video_lut_task(
    *,
    db: Session,
    user: User,
    video_url: str,
    node_id: str | None,
    project_id: str,
    script_table_node_id: str,
    lut_preset: str | None = None,
    lut_custom_url: str | None = None,
    team_id: str | None = None,
) -> str | None:
    from services.media_access import resolve_video_source_for_enhance

    url = (video_url or "").strip()
    if not url:
        return None

    lut_path = resolve_lut_file_path(lut_preset=lut_preset, lut_custom_url=lut_custom_url)
    if lut_path is None:
        return None

    try:
        resolve_video_source_for_enhance(db, user, url)
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(status_code=400, detail="视频源无效或无权访问") from exc

    check_concurrent_generations(db, user, slots_needed=1, team_id=team_id)
    try:
        check_and_consume(db, user.id, "video")
    except QuotaExceededError as e:
        raise HTTPException(status_code=429, detail=e.message) from e

    task_id = str(uuid.uuid4())
    label = f"video_lut {lut_preset or 'custom'}"
    create_task_record(
        db,
        task_id,
        "video_lut",
        "pending",
        user_id=user.id,
        team_id=team_id,
        prompt_text=label,
        comfyui_prompt_id=mock_generation.MOCK_PROMPT_ID
        if settings.agent_mock_generation
        else "lut",
        node_id=node_id,
    )
    db.commit()
    tasks_cache.invalidate_tasks_cache()

    if settings.agent_mock_generation:
        asyncio.create_task(
            mock_generation.run_mock_video_lut_task(
                task_id,
                url,
                lut_preset=lut_preset,
                lut_custom_url=lut_custom_url,
                failure_rate=settings.agent_mock_failure_rate,
            )
        )
    else:
        asyncio.create_task(
            run_video_lut_task(
                task_id,
                url,
                lut_preset=lut_preset,
                lut_custom_url=lut_custom_url,
                user_id=user.id,
            )
        )
    return task_id


async def run_video_lut_task(
    task_id: str,
    source_video_url: str,
    *,
    lut_preset: str | None,
    lut_custom_url: str | None,
    user_id: int,
) -> None:
    await asyncio.to_thread(
        _run_video_lut_sync,
        task_id,
        source_video_url,
        lut_preset,
        lut_custom_url,
        user_id,
    )


def _run_video_lut_sync(
    task_id: str,
    source_video_url: str,
    lut_preset: str | None,
    lut_custom_url: str | None,
    user_id: int,
) -> None:
    db = SessionLocal()
    try:
        task = db.get(Task, task_id)
        if not task:
            return
        from services.media_access import resolve_video_source_for_enhance
        from models import User

        user = db.get(User, user_id)
        if not user:
            task.status = "failed"
            task.error = "用户不存在"
            db.commit()
            return

        input_path = resolve_video_source_for_enhance(db, user, source_video_url)
        if input_path is None or not Path(input_path).is_file():
            task.status = "failed"
            task.error = "无法读取源视频"
            _release_task_slots(task)
            db.commit()
            return

        lut_path = resolve_lut_file_path(
            lut_preset=lut_preset, lut_custom_url=lut_custom_url
        )
        if lut_path is None:
            task.status = "failed"
            task.error = "LUT 文件无效"
            _release_task_slots(task)
            db.commit()
            return

        output_path = new_lut_output_path()
        apply_lut_to_video_file(Path(input_path), lut_path, output_path)
        task.status = "completed"
        task.result = f"/api/uploads/videos/{output_path.name}"
        task.error = None
        if hasattr(task, "lut_applied"):
            task.lut_applied = True
        _release_task_slots(task)
        db.commit()
        logger.info("video_lut task completed task_id=%s", task_id)
    except HTTPException as exc:
        db.rollback()
        task = db.get(Task, task_id)
        if task and task.status not in ("completed", "failed"):
            task.status = "failed"
            task.error = str(exc.detail)
            _release_task_slots(task)
            db.commit()
    except Exception:
        db.rollback()
        logger.exception("video_lut task error task_id=%s", task_id)
        task = db.get(Task, task_id)
        if task and task.status not in ("completed", "failed"):
            task.status = "failed"
            task.error = "LUT 处理内部错误"
            _release_task_slots(task)
            db.commit()
    finally:
        db.close()
