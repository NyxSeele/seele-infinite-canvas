"""G39: 视频完成后按 sound_note 生成音效并混入 mp4。"""

from __future__ import annotations

import asyncio
import logging
from pathlib import Path

from db.session import SessionLocal
from models import Task, User
from services.audiogen import generate_sfx_wav
from services.audio_mix import mix_sfx_into_video
from services.media_access import grant_output_access, resolve_video_source_for_enhance

logger = logging.getLogger(__name__)

UPLOADS_VIDEOS = Path(__file__).resolve().parent.parent / "uploads" / "videos"


async def maybe_apply_sound_note_mix(task_id: str) -> None:
    """后台任务：失败只记日志，不改失败态（保留无音轨成片）。"""
    try:
        await _apply_sound_note_mix(task_id)
    except Exception as exc:
        logger.exception("G39 sound_note mix failed task_id=%s: %s", task_id, exc)


async def _apply_sound_note_mix(task_id: str) -> None:
    db = SessionLocal()
    try:
        task = db.get(Task, task_id)
        if not task or task.status != "completed" or not task.result:
            return
        if "_sfx.mp4" in str(task.result):
            logger.info("G39 skip already mixed task_id=%s", task_id)
            return
        note = (task.sound_note or "").strip()
        if not note:
            return
        backend = (task.video_backend or "").strip().lower()
        if backend == "ltx2":
            logger.info("G39 skip mix for ltx2 task_id=%s", task_id)
            return

        user = db.get(User, task.user_id) if task.user_id else None
        if not user:
            logger.warning("G39 no user for task_id=%s", task_id)
            return

        video_url = task.result
        try:
            video_path = resolve_video_source_for_enhance(db, user, video_url)
        except Exception as exc:
            logger.warning("G39 resolve video failed task_id=%s: %s", task_id, exc)
            return
        if not video_path or not Path(video_path).is_file():
            logger.warning("G39 video path missing task_id=%s", task_id)
            return

        from comfyui import llm

        translated = await llm.translate_to_english(note, mode="video")
        en = (translated.get("positive") or note).strip()
        duration = _guess_duration_sec(video_path)

        wav_path = await asyncio.to_thread(
            generate_sfx_wav,
            en,
            duration=min(max(duration, 1.0), 15.0),
        )
        out_path = UPLOADS_VIDEOS / f"{Path(video_path).stem}_sfx.mp4"
        mixed = await asyncio.to_thread(
            mix_sfx_into_video,
            Path(video_path),
            Path(wav_path),
            out_path,
        )
        new_url = f"/api/uploads/videos/{mixed.name}"
        if task.user_id:
            grant_output_access(task.user_id, new_url)
        task.result = new_url
        db.commit()
        logger.info(
            "G39 mix ok task_id=%s result=%s en_prompt=%r",
            task_id,
            new_url,
            en[:80],
        )
    finally:
        db.close()


def _guess_duration_sec(video_path: Path) -> float:
    try:
        from services.video_enhance_probe import _ffmpeg_executable
        import subprocess
        import re

        proc = subprocess.run(
            [_ffmpeg_executable(), "-i", str(video_path)],
            capture_output=True,
            text=True,
            timeout=30,
        )
        text = (proc.stderr or "") + (proc.stdout or "")
        m = re.search(r"Duration:\s*(\d+):(\d+):(\d+(?:\.\d+)?)", text)
        if m:
            h, mi, s = int(m.group(1)), int(m.group(2)), float(m.group(3))
            return h * 3600 + mi * 60 + s
    except Exception:
        pass
    return 5.0
