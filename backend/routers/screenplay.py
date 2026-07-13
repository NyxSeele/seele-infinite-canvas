import asyncio
import json
import logging
import time
import uuid

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from core.dependencies import get_current_user
from db.session import get_db
from models import Task, User
from services.quota_service import create_task_record
from services.qwen import generate_outline, generate_shots
from services.screenplay_structure import structure_screenplay_from_text

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/screenplay", tags=["screenplay"])

TASK_TYPE_STRUCTURE = "sp_structure"
TASK_TYPE_SHOTS = "sp_shots"


class GenerateOutlineRequest(BaseModel):
    idea: str = Field(..., min_length=1)
    count: int = Field(1, ge=1, le=4)


class StructureFromTextRequest(BaseModel):
    text: str = Field(..., min_length=1)
    target_duration_sec: int | None = Field(default=None, ge=15, le=900)
    source_idea: str = Field(default="")


class GenerateShotsRequest(BaseModel):
    outline: str = Field(..., min_length=1)
    target_duration_sec: int | None = Field(
        default=None,
        ge=15,
        le=900,
        description="整片目标时长（秒），如用户要求 1 分钟则传 60",
    )


def _mark_done(db: Session, task_id: str, *, result: dict | None = None, error: str | None = None) -> None:
    task = db.get(Task, task_id)
    if not task:
        return
    if task.status == "cancelled":
        return
    if error:
        task.status = "failed"
        task.error = error[:2000]
        task.result = None
    else:
        task.status = "completed"
        task.error = None
        task.result = json.dumps(result or {}, ensure_ascii=False)
    db.commit()


async def _run_structure_task(
    task_id: str,
    text: str,
    target_duration_sec: int | None,
    source_idea: str,
) -> None:
    from db.session import SessionLocal

    db = SessionLocal()
    try:
        task = db.get(Task, task_id)
        if task:
            task.status = "processing"
            task.error = None
            db.commit()
        t0 = time.perf_counter()
        result = await structure_screenplay_from_text(
            text,
            target_duration_sec=target_duration_sec,
            source_idea=source_idea or "",
        )
        scenes = result.get("scenes") or []
        logger.info(
            "structure-from-text async ok task_id=%s in %.1fs scenes=%s",
            task_id,
            time.perf_counter() - t0,
            len(scenes),
        )
        _mark_done(db, task_id, result=result)
    except ValueError as exc:
        logger.warning("structure-from-text async failed task_id=%s: %s", task_id, exc)
        _mark_done(db, task_id, error=str(exc))
    except Exception as exc:
        logger.exception("structure-from-text async error task_id=%s", task_id)
        _mark_done(db, task_id, error=f"整理大纲失败: {str(exc)[:200]}")
    finally:
        db.close()


async def _run_shots_task(
    task_id: str,
    outline: str,
    target_duration_sec: int | None,
) -> None:
    from db.session import SessionLocal

    db = SessionLocal()
    try:
        task = db.get(Task, task_id)
        if task:
            task.status = "processing"
            task.error = None
            db.commit()
        result = await generate_shots(outline, target_duration_sec=target_duration_sec)
        payload = {
            "segments": result["segments"],
            "truncated": result.get("truncated", False),
            "target_video_duration_sec": result.get("target_video_duration_sec"),
            "duration_warning": result.get("duration_warning"),
        }
        logger.info(
            "generate-shots async ok task_id=%s segments=%s",
            task_id,
            len(payload["segments"] or []),
        )
        _mark_done(db, task_id, result=payload)
    except ValueError as exc:
        logger.warning("generate-shots async failed task_id=%s: %s", task_id, exc)
        _mark_done(db, task_id, error=str(exc))
    except Exception as exc:
        logger.exception("generate-shots async error task_id=%s", task_id)
        _mark_done(db, task_id, error=f"分镜生成失败: {str(exc)[:200]}")
    finally:
        db.close()


@router.post("/structure-from-text")
async def screenplay_structure_from_text(
    body: StructureFromTextRequest,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """将 LLM 剧本回复整理为大纲；立即返回 task_id，结果经 GET /api/tasks/{id} 轮询。"""
    text = body.text.strip()
    text_len = len(text)
    if not text:
        raise HTTPException(status_code=400, detail="请提供剧本文本")
    logger.info("structure-from-text: enqueue text_len=%s", text_len)

    task_id = str(uuid.uuid4())
    create_task_record(
        db,
        task_id,
        TASK_TYPE_STRUCTURE,
        "queued",
        user_id=user.id,
        prompt_text=text[:2000],
    )
    db.commit()
    asyncio.create_task(
        _run_structure_task(
            task_id,
            text,
            body.target_duration_sec,
            body.source_idea or "",
        )
    )
    return {"task_id": task_id, "status": "queued"}


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
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """分镜生成：立即返回 task_id，结果经 GET /api/tasks/{id} 轮询。"""
    outline = body.outline.strip()
    if not outline:
        raise HTTPException(status_code=400, detail="请提供剧本大纲")
    logger.info("generate-shots: enqueue outline_len=%s", len(outline))

    task_id = str(uuid.uuid4())
    create_task_record(
        db,
        task_id,
        TASK_TYPE_SHOTS,
        "queued",
        user_id=user.id,
        prompt_text=outline[:2000],
    )
    db.commit()
    asyncio.create_task(
        _run_shots_task(task_id, outline, body.target_duration_sec)
    )
    return {"task_id": task_id, "status": "queued"}
