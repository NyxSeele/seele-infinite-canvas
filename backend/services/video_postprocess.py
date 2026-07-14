"""视频完成后 G45 ReActor / G39 sound_note 后处理调度。"""

from __future__ import annotations

import asyncio

from models import Task


def should_schedule_video_postprocess(task: Task) -> bool:
    if not task or task.task_type != "video" or task.status != "completed":
        return False
    if bool(getattr(task, "use_reactor", False)):
        return True
    if not (task.sound_note or "").strip():
        return False
    return (task.video_backend or "").strip().lower() != "ltx2"


def schedule_video_postprocess(task: Task) -> None:
    """G45 逐帧换脸（若 use_reactor）→ 链式 G39 sound_note；仅 sound_note 时直接混音。"""
    if not should_schedule_video_postprocess(task):
        return
    if bool(getattr(task, "use_reactor", False)):
        from services.reactor_video import maybe_apply_reactor_video

        asyncio.create_task(maybe_apply_reactor_video(task.id))
        return
    from services.audiogen_postprocess import maybe_apply_sound_note_mix

    asyncio.create_task(maybe_apply_sound_note_mix(task.id))
