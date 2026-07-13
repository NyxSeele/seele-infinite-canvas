"""Seedance 异步视频任务：提交 Ark → 轮询 → 写 DB（仿 LUT/文本模式）。"""

from __future__ import annotations

import asyncio
import logging
import uuid
from typing import Any

from db.session import SessionLocal
from models import Task
from providers.seedance import SeedanceClient, SeedanceNotConfiguredError
from services.generation_slots import release_slots
from services.quota_service import create_task_record
from core.logging_setup import studio_print

logger = logging.getLogger(__name__)

POLL_INTERVAL_SEC = 5.0
POLL_MAX_ATTEMPTS = 120  # ~10 min


def _extract_video_url(payload: dict[str, Any]) -> str | None:
    if not isinstance(payload, dict):
        return None
    content = payload.get("content")
    if isinstance(content, dict):
        url = content.get("video_url") or content.get("url")
        if isinstance(url, str) and url.strip():
            return url.strip()
    for key in ("video_url", "url", "output"):
        val = payload.get(key)
        if isinstance(val, str) and val.startswith("http"):
            return val
    data = payload.get("data")
    if isinstance(data, dict):
        return _extract_video_url(data)
    return None


async def run_seedance_video_task(
    task_id: str,
    *,
    prompt: str,
    ratio: str,
    duration: int,
    resolution: str,
) -> None:
    client = SeedanceClient()
    db = SessionLocal()
    try:
        task = db.get(Task, task_id)
        if not task:
            return
        if not client.is_configured():
            task.status = "failed"
            task.error = "未配置 SEEDANCE_API_KEY"
            db.commit()
            release_slots(task.user_id, team_id=task.team_id, slots=1)
            return

        try:
            created = await client.create_task(
                prompt,
                ratio=ratio,
                duration=duration,
                resolution=resolution,
            )
        except SeedanceNotConfiguredError as e:
            task.status = "failed"
            task.error = str(e)
            db.commit()
            release_slots(task.user_id, team_id=task.team_id, slots=1)
            return
        except Exception as e:
            logger.exception("seedance create_task failed")
            task.status = "failed"
            task.error = f"Seedance 提交失败: {e}"
            db.commit()
            release_slots(task.user_id, team_id=task.team_id, slots=1)
            return

        external_id = str(created.get("id") or created.get("task_id") or "").strip()
        if not external_id:
            task.status = "failed"
            task.error = "Seedance 未返回 task id"
            db.commit()
            release_slots(task.user_id, team_id=task.team_id, slots=1)
            return

        task.comfyui_prompt_id = f"seedance:{external_id}"
        task.status = "running"
        db.commit()
        studio_print("seedance", f"queued external_id={external_id} task_id={task_id}")

        for _ in range(POLL_MAX_ATTEMPTS):
            await asyncio.sleep(POLL_INTERVAL_SEC)
            try:
                info = await client.get_task(external_id)
            except Exception as e:
                logger.warning("seedance poll error: %s", e)
                continue
            status = str(info.get("status") or "").lower()
            if status in ("succeeded", "success", "completed"):
                url = _extract_video_url(info)
                task = db.get(Task, task_id)
                if not task:
                    return
                if url:
                    task.status = "completed"
                    task.result = url
                    task.error = None
                    db.commit()
                    release_slots(task.user_id, team_id=task.team_id, slots=1)
                    if bool(getattr(task, "use_reactor", False)):
                        from services.reactor_video import maybe_apply_reactor_video

                        asyncio.create_task(maybe_apply_reactor_video(task_id))
                    elif (
                        (task.sound_note or "").strip()
                        and (task.video_backend or "").strip().lower() != "ltx2"
                    ):
                        from services.audiogen_postprocess import maybe_apply_sound_note_mix

                        asyncio.create_task(maybe_apply_sound_note_mix(task_id))
                else:
                    task.status = "failed"
                    task.error = "Seedance 完成但无 video_url"
                    db.commit()
                    release_slots(task.user_id, team_id=task.team_id, slots=1)
                return
            if status in ("failed", "cancelled", "canceled", "error"):
                task = db.get(Task, task_id)
                if not task:
                    return
                task.status = "failed"
                task.error = str(info.get("error") or info.get("message") or status)
                db.commit()
                release_slots(task.user_id, team_id=task.team_id, slots=1)
                return

        task = db.get(Task, task_id)
        if task and task.status in ("pending", "queued", "running"):
            task.status = "failed"
            task.error = "Seedance 轮询超时"
            db.commit()
            release_slots(task.user_id, team_id=task.team_id, slots=1)
    finally:
        db.close()


async def queue_seedance_video_task(
    db,
    *,
    user_id: int,
    team_id: int | None,
    node_id: str | None,
    prompt: str,
    ratio: str,
    duration: int,
    resolution: str,
    sound_note: str | None = None,
    use_reactor: bool = False,
    reactor_face_image: str | None = None,
    video_backend: str = "seedance",
) -> str:
    task_id = str(uuid.uuid4())
    create_task_record(
        db,
        task_id,
        "video",
        "pending",
        user_id=user_id,
        team_id=team_id,
        prompt_text=prompt,
        comfyui_prompt_id="seedance",
        node_id=node_id,
        sound_note=sound_note,
        video_backend=video_backend,
        use_reactor=use_reactor,
        reactor_face_image=reactor_face_image,
    )
    asyncio.create_task(
        run_seedance_video_task(
            task_id,
            prompt=prompt,
            ratio=ratio,
            duration=int(duration),
            resolution=str(resolution or "720p"),
        )
    )
    return task_id
