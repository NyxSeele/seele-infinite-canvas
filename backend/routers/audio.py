"""G39: POST /api/audio/generate — 中文 prompt → Qwen 译英 → AudioGen wav。"""

from __future__ import annotations

import asyncio
import logging
from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from core.dependencies import get_current_user
from models import User
from services.audiogen import audiogen_available, generate_sfx_wav
from services.media_access import grant_output_access

logger = logging.getLogger(__name__)

router = APIRouter(tags=["audio"])

UPLOADS_AUDIO = Path(__file__).resolve().parent.parent / "uploads" / "audio"


class AudioGenerateRequest(BaseModel):
    prompt: str = Field(..., description="中文音效描述")
    duration: float = Field(default=5.0, ge=0.5, le=30.0, description="时长（秒）")


@router.post("/api/audio/generate")
async def generate_audio(
    body: AudioGenerateRequest,
    user: User = Depends(get_current_user),
):
    prompt = (body.prompt or "").strip()
    if not prompt:
        raise HTTPException(status_code=400, detail="请填写音效描述")
    if not audiogen_available():
        raise HTTPException(status_code=503, detail="AudioGen 模型未就绪")

    from comfyui import llm

    translated = await llm.translate_to_english(prompt, mode="video")
    en = (translated.get("positive") or prompt).strip()
    translate_error = translated.get("error")

    try:
        wav_path = await asyncio.to_thread(
            generate_sfx_wav,
            en,
            duration=float(body.duration),
        )
    except Exception as exc:
        logger.exception("AudioGen generate failed: %s", exc)
        raise HTTPException(status_code=500, detail=f"音效生成失败: {exc}") from exc

    url = f"/api/uploads/audio/{wav_path.name}"
    grant_output_access(user.id, url)
    return {
        "url": url,
        "filename": wav_path.name,
        "duration": float(body.duration),
        "prompt_zh": prompt,
        "prompt_en": en,
        "translate_error": translate_error,
    }
