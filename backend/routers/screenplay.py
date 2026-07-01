import logging
import time

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from core.dependencies import get_current_user
from models import User
from services.qwen import generate_outline, generate_shots
from services.screenplay_structure import structure_screenplay_from_text

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/screenplay", tags=["screenplay"])


class GenerateOutlineRequest(BaseModel):
    idea: str = Field(..., min_length=1)
    count: int = Field(1, ge=1, le=4)


class StructureFromTextRequest(BaseModel):
    text: str = Field(..., min_length=1)
    target_duration_sec: int | None = Field(default=None, ge=15, le=900)
    source_idea: str = Field(default="")


@router.post("/structure-from-text")
async def screenplay_structure_from_text(
    body: StructureFromTextRequest,
    _user: User = Depends(get_current_user),
):
    """将 LLM 剧本回复整理为带时间轴与导演字段的大纲 scenes。"""
    text_len = len(body.text.strip())
    logger.info("structure-from-text: start text_len=%s", text_len)
    t0 = time.perf_counter()
    try:
        result = await structure_screenplay_from_text(
            body.text.strip(),
            target_duration_sec=body.target_duration_sec,
            source_idea=body.source_idea or "",
        )
    except ValueError as exc:
        logger.warning(
            "structure-from-text: failed in %.1fs: %s",
            time.perf_counter() - t0,
            exc,
        )
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception as exc:
        logger.exception(
            "structure-from-text: error in %.1fs",
            time.perf_counter() - t0,
        )
        raise HTTPException(
            status_code=500,
            detail=f"整理大纲失败: {str(exc)[:200]}",
        ) from exc
    scenes = result.get("scenes") or []
    logger.info(
        "structure-from-text: ok in %.1fs scenes=%s",
        time.perf_counter() - t0,
        len(scenes),
    )
    return result


class GenerateShotsRequest(BaseModel):
    outline: str = Field(..., min_length=1)
    target_duration_sec: int | None = Field(
        default=None,
        ge=15,
        le=900,
        description="整片目标时长（秒），如用户要求 1 分钟则传 60",
    )


@router.post("/generate-outline")
async def screenplay_generate_outline(
    body: GenerateOutlineRequest,
    _user: User = Depends(get_current_user),
):
    idea = body.idea.strip()
    if not idea:
        raise HTTPException(status_code=400, detail="请提供创意内容")
    try:
        result = await generate_outline(idea, count=body.count)
    except ValueError as exc:
        if "JSON" in str(exc):
            logger.error("JSON parse failed. Raw response: (see services.qwen log)")
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(
            status_code=500,
            detail=f"剧本生成失败: {str(exc)[:200]}",
        ) from exc
    return {
        "title": result["title"],
        "scenes": result["scenes"],
        "versions": result.get("versions"),
        "truncated": result.get("truncated", False),
    }


@router.post("/generate-shots")
async def screenplay_generate_shots(
    body: GenerateShotsRequest,
    _user: User = Depends(get_current_user),
):
    logger.info("generate-shots called, outline length: %s", len(body.outline))
    outline = body.outline.strip()
    if not outline:
        raise HTTPException(status_code=400, detail="请提供剧本大纲")
    try:
        result = await generate_shots(
            outline, target_duration_sec=body.target_duration_sec
        )
    except ValueError as exc:
        if "JSON" in str(exc):
            logger.error("JSON parse failed. Raw response: (see services.qwen log)")
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(
            status_code=500,
            detail=f"分镜生成失败: {str(exc)[:200]}",
        ) from exc
    return {
        "segments": result["segments"],
        "truncated": result.get("truncated", False),
        "target_video_duration_sec": result.get("target_video_duration_sec"),
        "duration_warning": result.get("duration_warning"),
    }
