"""Short-video factory API.

Environment:
  SHORT_VIDEO_MOCK_LLM=1   — mock script segments (no LLM network)
  SHORT_VIDEO_MOCK_TTS=1   — mock TTS duration/cues (no Edge TTS network)
  SHORT_VIDEO_MOCK_STOCK=1 — mock stock clips (no Pexels network)
  PEXELS_API_KEY           — Pexels API key(s), comma-separated for rotation
"""

from __future__ import annotations

import asyncio
import uuid
from pathlib import Path
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from core.dependencies import get_current_user
from db.session import get_db
from models import Task, User
from services.quota_service import create_task_record
from services.short_video_factory import DEFAULT_VOICE_NAME, OUTPUT_ROOT, run_short_video_job

router = APIRouter(tags=["short-video"])


class ShortVideoGenerateRequest(BaseModel):
    topic: str = Field(..., min_length=1, max_length=500)
    segment_count: int = Field(default=3, ge=1, le=12)
    aspect: str = Field(default="9:16")
    burn_captions: bool = False
    bgm: str = Field(default="none", description='BGM: "none" | "default" | absolute path')
    enable_tts: bool = True
    voice_name: str = Field(default=DEFAULT_VOICE_NAME, min_length=1, max_length=120)
    visual_source: Literal["slide", "stock"] = "slide"


def _resolve_task_video_path(task_id: str) -> Path:
    task_dir = (OUTPUT_ROOT / task_id).resolve()
    final_path = (task_dir / "final.mp4").resolve()
    root = OUTPUT_ROOT.resolve()
    if not str(final_path).startswith(str(root)) or not final_path.is_file():
        raise HTTPException(status_code=404, detail="成片文件不存在")
    return final_path


@router.post("/api/short-video/generate")
async def generate_short_video(
    body: ShortVideoGenerateRequest,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    topic = body.topic.strip()
    if not topic:
        raise HTTPException(status_code=400, detail="请填写 topic")
    task_id = str(uuid.uuid4())
    create_task_record(
        db,
        task_id,
        "short_video",
        "queued",
        user_id=user.id,
        prompt_text=topic,
        generation_params={
            "segment_count": body.segment_count,
            "aspect": body.aspect,
            "burn_captions": body.burn_captions,
            "bgm": body.bgm,
            "enable_tts": body.enable_tts,
            "voice_name": body.voice_name,
            "visual_source": body.visual_source,
        },
    )
    db.commit()

    asyncio.create_task(
        run_short_video_job(
            task_id,
            topic=topic,
            segment_count=body.segment_count,
            aspect=body.aspect,
            burn_captions=body.burn_captions,
            bgm=body.bgm,
            enable_tts=body.enable_tts,
            voice_name=body.voice_name,
            visual_source=body.visual_source,
        )
    )
    return {"task_id": task_id, "status": "queued"}


@router.get("/api/short-video/{task_id}")
async def get_short_video_task(
    task_id: str,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    task = db.get(Task, task_id)
    if not task or task.user_id != user.id:
        raise HTTPException(status_code=404, detail="任务不存在")
    if task.task_type != "short_video":
        raise HTTPException(status_code=404, detail="任务类型不匹配")
    payload = {
        "task_id": task.id,
        "status": task.status,
        "error": task.error,
    }
    if task.status == "completed" and task.result:
        payload["result_path"] = task.result
        payload["result_url"] = f"/api/short-video/{task_id}/file"
    return payload


@router.get("/api/short-video/{task_id}/file")
async def get_short_video_file(
    task_id: str,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    task = db.get(Task, task_id)
    if not task or task.user_id != user.id:
        raise HTTPException(status_code=404, detail="任务不存在")
    if task.task_type != "short_video":
        raise HTTPException(status_code=404, detail="任务类型不匹配")
    if task.status != "completed":
        raise HTTPException(status_code=409, detail="任务尚未完成")
    final_path = _resolve_task_video_path(task_id)
    return FileResponse(final_path, media_type="video/mp4", filename="final.mp4")
