"""画风参考异步任务：启动时回收僵尸 processing 任务。"""

from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone

from sqlalchemy.orm import Session

from models import Task

logger = logging.getLogger(__name__)

STYLE_REF_TASK_TYPE = "style_ref"
STALE_STYLE_REF_MINUTES = 5
RECOVERY_ERROR = "风格分析中断（服务重启或超时），请重新上传参考视频"


def recover_orphaned_style_ref_tasks_on_boot(db: Session) -> int:
    """进程重启后，所有未完成的 style_ref 异步任务均视为中断。"""
    rows = (
        db.query(Task)
        .filter(
            Task.task_type == STYLE_REF_TASK_TYPE,
            Task.status.in_(("pending", "processing", "running", "queued")),
        )
        .all()
    )
    if not rows:
        return 0

    now = datetime.now(timezone.utc)
    for task in rows:
        task.status = "failed"
        task.error = RECOVERY_ERROR
        task.result = None
        task.completed_at = now
    db.commit()
    logger.warning("recovered %s orphaned style_ref task(s) on boot", len(rows))
    return len(rows)


def recover_stale_style_ref_tasks(
    db: Session,
    *,
    max_age_minutes: int = STALE_STYLE_REF_MINUTES,
) -> int:
    cutoff = datetime.now(timezone.utc) - timedelta(minutes=max_age_minutes)
    rows = (
        db.query(Task)
        .filter(
            Task.task_type == STYLE_REF_TASK_TYPE,
            Task.status.in_(("pending", "processing", "running", "queued")),
            Task.created_at < cutoff,
        )
        .all()
    )
    if not rows:
        return 0

    now = datetime.now(timezone.utc)
    for task in rows:
        task.status = "failed"
        task.error = RECOVERY_ERROR
        task.result = None
        task.completed_at = now
    db.commit()
    logger.warning(
        "recovered %s stale style_ref task(s) older than %sm",
        len(rows),
        max_age_minutes,
    )
    return len(rows)
