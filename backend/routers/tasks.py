import asyncio
import base64
import logging
import re
import traceback
import uuid
from pathlib import Path

import httpx
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from comfyui import client as comfyui
from core.datetime_utils import to_utc_iso
from db.session import get_db
from core.dependencies import get_current_user
from models import RegisteredModel, Task, User
from models.team import Team
from services.team_service import get_member_role
from providers import comfyui as comfyui_image
from providers.qwen import call_openai_compatible
from schemas.tasks import (
    OptimizePromptRequest,
    SubmitRequest,
    SubmitVideoRequest,
    CanvasTextRequest,
    CanvasImageRequest,
    CanvasVideoRequest,
    VideoEnhanceRequest,
    VideoEnhanceRecommendRequest,
    VideoEnhanceRecommendResponse,
    VideoLutRequest,
)
from services.generation_guard import (
    check_concurrent_generations,
    reconcile_active_tasks_from_comfyui,
)
from services.media_access import append_media_ticket, grant_output_access, issue_media_ticket
from services.prompt import maybe_optimize_prompt
from services.quota_service import (
    QuotaExceededError,
    check_and_consume,
    create_task_record,
)
from model_registry import (
    MODEL_MAP,
    resolve_image_dimensions_for_model,
    resolve_video_backend,
    resolve_video_enhance_workflow,
    VIDEO_ENHANCE_REALESRGAN_ID,
    VIDEO_ENHANCE_SEEDVR2_ID,
)
from services import mock_generation
from services import tasks_cache
from services.mention_context import enrich_prompt, resolve_mentions, strip_mention_tokens
from core.logging_setup import studio_print
from trace_bus import extract_workflow_trace, push_trace


_MEDIA_TASK_TYPES = ("image", "video", "video_enhance", "video_lut")


def _merge_negative_prompt(built: str, optimized: str) -> str:
    """保留分镜预构建 negative（含二次元排除项），与 L3 结果合并。"""
    chunks: list[str] = []
    for raw in (optimized, built):
        for part in (raw or "").split(","):
            p = part.strip()
            if p and p not in chunks:
                chunks.append(p)
    return ", ".join(chunks)

router = APIRouter(tags=["tasks"])

logger = logging.getLogger(__name__)


def _sign_result_url_for_user(url: str | None, user_id: int) -> str | None:
    if not url or not user_id:
        return url
    grant_output_access(user_id, url)
    ticket = issue_media_ticket(user_id)["media_ticket"]
    if url.startswith("http://") or url.startswith("https://"):
        return append_media_ticket(url, ticket)
    if url.startswith("/"):
        return append_media_ticket(url, ticket)
    return append_media_ticket(f"/api/view?filename={url}&type=output", ticket)

# 画布同一 node_id 仅允许一条「进行中」任务；新提交前将旧记录标为终态
_ACTIVE_TASK_STATUSES = frozenset(
    {"pending", "queued", "running", "processing"}
)
_TERMINAL_TASK_STATUSES = frozenset(
    {"completed", "failed", "cancelled", "timeout"}
)


def _release_stale_node_tasks(
    db: Session,
    node_id: str | None,
    user_id: int,
    *,
    reason: str = "被新任务取代",
) -> int:
    """将同一画布节点上未结束的任务标为 failed，避免阻塞新提交。"""
    if not node_id:
        return 0
    rows = (
        db.query(Task)
        .filter(
            Task.node_id == node_id,
            Task.user_id == user_id,
            Task.status.in_(list(_ACTIVE_TASK_STATUSES)),
        )
        .all()
    )
    for task in rows:
        _mark_task_terminal(task, status="failed", error=reason)
    if rows:
        logger.info(
            "released %s stale task(s) for node_id=%s user_id=%s",
            len(rows),
            node_id,
            user_id,
        )
    return len(rows)


async def _resolve_image_result_from_history(
    comfy_prompt_id: str,
    user_id: int,
) -> str | None:
    """从 ComfyUI history 解析图片 view URL（与 providers.comfyui 逻辑互补）。"""
    from comfyui.client import _view_url_for_media

    raw = await comfyui_image.get_image_result(comfy_prompt_id)
    if isinstance(raw, str) and raw.strip():
        url = _view_url_for_media({"filename": raw.strip(), "type": "output"})
        return _sign_result_url_for_user(url, user_id)
    return None


def _mark_task_terminal(
    task: Task,
    *,
    status: str,
    error: str | None = None,
    result: str | None = None,
) -> None:
    """写入终态，供轮询与僵尸释放逻辑一致使用。"""
    was_active = task.status in _ACTIVE_TASK_STATUSES
    task.status = status
    task.error = error[:2000] if error else None
    if result is not None:
        task.result = result
    elif status in _TERMINAL_TASK_STATUSES and status != "completed":
        task.result = None
    if was_active and status in _TERMINAL_TASK_STATUSES:
        from services.generation_slots import release_slots

        release_slots(task.user_id, team_id=task.team_id)


def _release_acquired_slots(
    user_id: int,
    *,
    team_id: str | None,
    slots: int,
) -> None:
    if slots <= 0:
        return
    from services.generation_slots import release_slots

    release_slots(user_id, team_id=team_id, slots=slots)


@router.post("/api/optimize-prompt")
async def optimize_prompt_api(body: OptimizePromptRequest):
    text = body.text.strip()
    if not text:
        raise HTTPException(status_code=400, detail="请填写画面描述")

    mode = body.mode if body.mode in ("image", "video") else "image"

    try:
        from comfyui import llm

        return await asyncio.wait_for(
            llm.optimize_prompt(text, mode),
            timeout=settings.optimize_timeout,
        )
    except asyncio.TimeoutError:
        return {
            "positive": text,
            "negative": "worst quality, low quality, blurry",
            "error": "优化超时",
        }


async def _submit_image_task(body: SubmitRequest, user: User, db: Session):
    check_concurrent_generations(db, user, team_id=body.team_id)
    prompt = body.prompt.strip()
    if not prompt:
        raise HTTPException(status_code=400, detail="请填写画面描述")

    if body.style not in comfyui.STYLE_SUFFIXES:
        raise HTTPException(status_code=400, detail="无效的风格选项")

    try:
        check_and_consume(db, user.id, "image")
    except QuotaExceededError as e:
        raise HTTPException(status_code=429, detail=e.message) from e

    positive, negative, optimized, _translate_note = await maybe_optimize_prompt(
        prompt, body.negative_prompt, "image", body.auto_optimize
    )

    try:
        task_id, client_id = await comfyui.submit_prompt(
            prompt=positive,
            negative_prompt=negative,
            style=body.style,
            steps=comfyui.DEFAULT_STEPS,
            width=body.width,
            height=body.height,
            client_id=body.client_id,
            raw_prompt=optimized,
            reference_image=body.reference_image,
        )
    except ValueError as e:
        db.rollback()
        raise HTTPException(status_code=400, detail=str(e)) from e
    except httpx.ConnectError:
        db.rollback()
        raise HTTPException(
            status_code=503,
            detail="ComfyUI 服务未启动，请先启动 ComfyUI（端口 8000）",
        )
    except httpx.HTTPStatusError as e:
        db.rollback()
        raise HTTPException(
            status_code=502,
            detail=f"ComfyUI 返回错误: {e.response.status_code}",
        ) from e
    except Exception as e:
        db.rollback()
        raise HTTPException(status_code=500, detail=f"提交失败: {e}") from e

    create_task_record(
        db,
        task_id,
        "image",
        "pending",
        user_id=user.id,
        team_id=body.team_id,
        prompt_text=prompt,
    )
    db.commit()
    tasks_cache.invalidate_tasks_cache()

    return {
        "task_id": task_id,
        "client_id": client_id,
        "message": "提交成功",
    }


@router.post("/api/submit")
@router.post("/api/submit/image")
async def submit_task(
    body: SubmitRequest,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    return await _submit_image_task(body, user, db)


async def _submit_video_task(body: SubmitVideoRequest, user: User, db: Session):
    check_concurrent_generations(db, user, team_id=body.team_id)
    prompt = body.prompt.strip()
    if not prompt:
        raise HTTPException(status_code=400, detail="请填写画面描述")

    if body.duration not in (3, 5):
        raise HTTPException(status_code=400, detail="视频时长仅支持 3 秒或 5 秒")

    if body.mode not in ("text2video", "image2video"):
        raise HTTPException(status_code=400, detail="无效的生成模式")

    if body.mode == "image2video" and not body.image:
        raise HTTPException(status_code=400, detail="图生视频需要上传图片")

    width, height = comfyui.align_ltx_dimensions(body.width, body.height)

    try:
        check_and_consume(db, user.id, "video")
    except QuotaExceededError as e:
        raise HTTPException(status_code=429, detail=e.message) from e

    positive, negative, optimized, _translate_note = await maybe_optimize_prompt(
        prompt, body.negative_prompt, "video", body.auto_optimize
    )

    try:
        task_id, client_id, _workflow = await comfyui.submit_video_prompt(
            prompt=positive,
            negative_prompt=negative,
            duration=body.duration,
            width=width,
            height=height,
            mode=body.mode,
            image_b64=body.image,
            client_id=body.client_id,
            raw_prompt=optimized,
        )
    except ValueError as e:
        db.rollback()
        raise HTTPException(status_code=400, detail=str(e)) from e
    except httpx.ConnectError:
        db.rollback()
        raise HTTPException(
            status_code=503,
            detail="ComfyUI 服务未启动，请先启动 ComfyUI（端口 8000）",
        )
    except httpx.HTTPStatusError as e:
        db.rollback()
        raise HTTPException(
            status_code=502,
            detail=f"ComfyUI 返回错误: {e.response.status_code}",
        ) from e
    except Exception as e:
        db.rollback()
        raise HTTPException(status_code=500, detail=f"提交失败: {e}") from e

    create_task_record(
        db,
        task_id,
        "video",
        "pending",
        user_id=user.id,
        team_id=body.team_id,
        prompt_text=prompt,
    )
    db.commit()
    tasks_cache.invalidate_tasks_cache()

    return {
        "task_id": task_id,
        "client_id": client_id,
        "message": "提交成功",
    }


@router.post("/api/submit/video")
async def submit_video_task(
    body: SubmitVideoRequest,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    return await _submit_video_task(body, user, db)


@router.get("/api/tasks/records")
def list_task_records(
    team_id: str | None = Query(default=None),
    limit: int = Query(default=80, ge=1, le=200),
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """数据库任务记录（含团队 tag），供历史/审计初版。"""
    if team_id:
        if not get_member_role(db, team_id, user.id):
            raise HTTPException(status_code=403, detail="无权访问该团队任务")
        rows = (
            db.query(Task, Team, User)
            .outerjoin(Team, Team.id == Task.team_id)
            .outerjoin(User, User.id == Task.user_id)
            .filter(Task.team_id == team_id)
            .order_by(Task.created_at.desc())
            .limit(limit)
            .all()
        )
    else:
        rows = (
            db.query(Task, Team, User)
            .outerjoin(Team, Team.id == Task.team_id)
            .join(User, User.id == Task.user_id)
            .filter(Task.user_id == user.id, Task.team_id.is_(None))
            .order_by(Task.created_at.desc())
            .limit(limit)
            .all()
        )
    return {
        "records": [
            {
                "id": task.id,
                "task_type": task.task_type,
                "status": task.status,
                "prompt_text": task.prompt_text,
                "node_id": task.node_id,
                "team_id": task.team_id,
                "team_name": team.name if team else None,
                "user_id": task.user_id,
                "username": owner.username if owner else None,
                "created_at": to_utc_iso(task.created_at),
                "result": (
                    _sign_result_url_for_user(task.result, user.id)
                    if task.status == "completed"
                    and task.task_type in _MEDIA_TASK_TYPES
                    and task.result
                    else None
                ),
            }
            for task, team, owner in rows
        ]
    }


@router.get("/api/tasks/{task_id}")
async def get_task_by_id(
    task_id: str,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """查询单个画布任务状态（文本/图像生成轮询等）。"""
    task = db.get(Task, task_id)
    if not task:
        raise HTTPException(status_code=404, detail="任务不存在")
    if task.user_id is not None and task.user_id != user.id and user.role != "admin":
        raise HTTPException(status_code=403, detail="无权访问该任务")

    if task.task_type in _MEDIA_TASK_TYPES and task.status == "completed" and task.result:
        return {
            "task_id": task.id,
            "status": "completed",
            "progress": 100,
            "result": _sign_result_url_for_user(task.result, user.id),
            "error": None,
        }

    if task.comfyui_prompt_id == mock_generation.MOCK_PROMPT_ID:
        if task.status == "failed":
            return {
                "task_id": task.id,
                "status": "failed",
                "progress": 0,
                "result": None,
                "error": task.error,
            }
        return {
            "task_id": task.id,
            "status": task.status,
            "progress": 50 if task.status in ("pending", "queued", "running") else 0,
            "result": None,
            "error": None,
        }

    comfy_prompt_id = task.comfyui_prompt_id or (
        task.id if task.task_type in _MEDIA_TASK_TYPES else None
    )

    if comfy_prompt_id and task.task_type in _MEDIA_TASK_TYPES:
        if task.status in ("pending", "queued", "running"):
            exec_info = await comfyui.get_prompt_execution_status(comfy_prompt_id)
            api_status = exec_info.get("status") or task.status
            progress = int(exec_info.get("progress") or 0)
            studio_print(
                "poll",
                f"GET /api/tasks/{task_id} type={task.task_type} "
                f"comfy_prompt_id={comfy_prompt_id} api_status={api_status} "
                f"progress={progress} has_result={bool(exec_info.get('result'))}",
            )

            if api_status == "completed" and exec_info.get("result"):
                _mark_task_terminal(
                    task,
                    status="completed",
                    result=_sign_result_url_for_user(
                        exec_info["result"],
                        task.user_id or user.id,
                    ),
                )
                db.commit()
                studio_print(
                    task.task_type,
                    f"任务完成 task_id={task_id} comfy_prompt_id={comfy_prompt_id} "
                    f"result={task.result}",
                )
                return {
                    "task_id": task.id,
                    "status": "completed",
                    "progress": 100,
                    "result": task.result,
                    "error": None,
                }

            if api_status == "failed":
                _mark_task_terminal(
                    task,
                    status="failed",
                    error=exec_info.get("error") or "生成失败",
                )
                db.commit()
                studio_print(
                    task.task_type,
                    f"任务失败 task_id={task_id} error={task.error}",
                )
                return {
                    "task_id": task.id,
                    "status": "failed",
                    "progress": progress,
                    "result": None,
                    "error": task.error,
                }

            if api_status == "completed" and not exec_info.get("result"):
                fallback_result = await _resolve_image_result_from_history(
                    comfy_prompt_id,
                    task.user_id or user.id,
                )
                if fallback_result:
                    _mark_task_terminal(
                        task,
                        status="completed",
                        result=fallback_result,
                    )
                    db.commit()
                    studio_print(
                        "poll",
                        f"history 回退命中图片 task_id={task_id} result={fallback_result}",
                    )
                    return {
                        "task_id": task.id,
                        "status": "completed",
                        "progress": 100,
                        "result": task.result,
                        "error": None,
                    }
                err = "ComfyUI 已完成但未返回图片 URL"
                _mark_task_terminal(task, status="failed", error=err)
                db.commit()
                studio_print("poll", f"任务异常完成无输出 task_id={task_id}")
                return {
                    "task_id": task.id,
                    "status": "failed",
                    "progress": progress,
                    "result": None,
                    "error": err,
                }

            if api_status in ("running", "pending"):
                if task.status != api_status:
                    task.status = api_status
                    db.commit()
                return {
                    "task_id": task.id,
                    "status": api_status,
                    "progress": progress,
                    "stage": exec_info.get("stage"),
                    "message": exec_info.get("message"),
                    "result": None,
                    "error": None,
                }

    return {
        "task_id": task.id,
        "status": task.status,
        "progress": 0,
        "result": task.result,
        "error": task.error,
    }


@router.get("/api/tasks")
async def get_tasks(
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    user_task_ids = {t.id for t in db.query(Task).filter(Task.user_id == user.id).all()}

    cached, hit = tasks_cache.get_cached_tasks()
    if hit:
        tasks = cached
    else:
        tasks = await comfyui.get_tasks()
        tasks_cache.set_cached_tasks(tasks)

    if user.role != "admin":
        tasks = [t for t in tasks if t.get("id") in user_task_ids]
    return {"tasks": tasks}


@router.post("/api/task/{task_id}/cancel")
async def cancel_task(
    task_id: str,
    db: Session = Depends(get_db),
):
    """取消 ComfyUI 队列任务；画布 task_id 会解析为 comfyui_prompt_id。"""
    comfy_id = task_id
    task = db.get(Task, task_id)
    if task and task.comfyui_prompt_id:
        comfy_id = task.comfyui_prompt_id
        _mark_task_terminal(
            task,
            status="cancelled",
            error="用户已停止生成",
        )
        db.commit()
    try:
        await comfyui.cancel_task(comfy_id)
    except httpx.HTTPStatusError as e:
        raise HTTPException(
            status_code=502,
            detail=f"取消失败: {e.response.text}",
        ) from e
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"取消失败: {e}") from e

    tasks_cache.invalidate_tasks_cache()
    return {"message": "已取消", "task_id": task_id}


@router.get("/api/progress")
async def get_progress():
    return await comfyui.get_progress()


# ─────────────────────────────────────────────────────────────────────────────
# Canvas task routes  (text / image / video)
# ─────────────────────────────────────────────────────────────────────────────

# Resolution lookup: (ratio, quality) → (width, height)
# Image 3K = 2K × 1.5 取整
_IMAGE_2K: dict[str, tuple[int, int]] = {
    "1:1":  (2048, 2048),
    "4:3":  (2560, 1920),
    "3:4":  (1920, 2560),
    "16:9": (2730, 1536),
    "9:16": (1536, 2730),
    "3:2":  (2730, 1820),
    "2:3":  (1820, 2730),
    "21:9": (3072, 1318),
}


def _scale_resolution(w: int, h: int, factor: float = 1.5) -> tuple[int, int]:
    return int(w * factor), int(h * factor)


RESOLUTION_MAP: dict[tuple[str, str], tuple[int, int]] = {}
for _ratio, (_w, _h) in _IMAGE_2K.items():
    RESOLUTION_MAP[(_ratio, "2K")] = (_w, _h)
    RESOLUTION_MAP[(_ratio, "3K")] = _scale_resolution(_w, _h)

RESOLUTION_MAP.update({
    ("16:9", "720P"):  (1280, 720),
    ("9:16", "720P"):  (720, 1280),
    ("1:1",  "720P"):  (720, 720),
    ("16:9", "1080P"): (1920, 1080),
    ("9:16", "1080P"): (1080, 1920),
    ("1:1",  "1080P"): (1080, 1080),
})

def resolve_canvas_image_dimensions(
    model_id: str, ratio: str, quality: str | None
) -> tuple[int, int]:
    """画布图像：按模型 recommended_resolutions 解析宽高。"""
    try:
        return resolve_image_dimensions_for_model(model_id, ratio, quality)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e


# ── Text LLM dispatch ─────────────────────────────────────────────────────────

async def call_openai(model: str, prompt: str, count: int, **kwargs) -> dict:
    """占位：调用 OpenAI GPT 系列模型。"""
    raise NotImplementedError(f"OpenAI 调用尚未实现 (model={model})")


async def call_anthropic(model: str, prompt: str, count: int, **kwargs) -> dict:
    """占位：调用 Anthropic Claude 系列模型。"""
    raise NotImplementedError(f"Anthropic 调用尚未实现 (model={model})")


# ── Image model dispatch stubs ────────────────────────────────────────────────

async def call_stable_diffusion(
    model: str, prompt: str, width: int, height: int, count: int,
    reference_image: str | None = None, **kwargs
) -> dict:
    """占位：调用 Stable Diffusion / SDXL 本地模型。"""
    raise NotImplementedError(f"Stable Diffusion 调用尚未实现 (model={model})")


async def call_flux(
    model: str, prompt: str, width: int, height: int, count: int,
    reference_image: str | None = None, **kwargs
) -> dict:
    """占位：调用 FLUX 系列模型 (flux-dev / flux-schnell)。"""
    raise NotImplementedError(f"FLUX 调用尚未实现 (model={model})")


async def call_hidream(
    model: str, prompt: str, width: int, height: int, count: int,
    reference_image: str | None = None, **kwargs
) -> dict:
    """占位：调用 HiDream 模型。"""
    raise NotImplementedError(f"HiDream 调用尚未实现 (model={model})")


async def call_jimeng(
    model: str, prompt: str, width: int, height: int, count: int,
    reference_image: str | None = None, **kwargs
) -> dict:
    """占位：调用即梦（Jimeng）系列模型。"""
    raise NotImplementedError(f"即梦调用尚未实现 (model={model})")


# ── Video model dispatch stubs ────────────────────────────────────────────────

async def call_wan(
    model: str, prompt: str, width: int, height: int,
    duration: int, audio: bool, generation_mode: str, count: int, **kwargs
) -> dict:
    """占位：调用 Wan 2.6 视频生成模型。"""
    raise NotImplementedError(f"Wan 调用尚未实现 (model={model})")


async def call_ltx(
    model: str, prompt: str, width: int, height: int,
    duration: int, audio: bool, generation_mode: str, count: int, **kwargs
) -> dict:
    """占位：调用 LTX-Video 视频生成模型。"""
    raise NotImplementedError(f"LTX-Video 调用尚未实现 (model={model})")


async def call_hunyuan(
    model: str, prompt: str, width: int, height: int,
    duration: int, audio: bool, generation_mode: str, count: int, **kwargs
) -> dict:
    """占位：调用 HunyuanVideo 视频生成模型。"""
    raise NotImplementedError(f"HunyuanVideo 调用尚未实现 (model={model})")


# ── Canvas: text generation ───────────────────────────────────────────────────

async def _run_text_generation(
    task_id: str,
    model: str,
    prompt: str,
    count: int,
    user_id: int,
    *,
    screenplay_mode: bool = False,
) -> None:
    """后台执行文本生成并更新任务状态。"""
    from db.session import SessionLocal

    db = SessionLocal()
    try:
        task = db.get(Task, task_id)
        if task:
            task.status = "processing"
            task.error = None
            db.commit()

        row = (
            db.query(RegisteredModel)
            .filter(RegisteredModel.id == model, RegisteredModel.enabled.is_(True))
            .first()
        )
        if not row:
            raise ValueError(f"模型 {model} 未启用或不存在")
        model_type = getattr(row, "type", None)
        if model_type == "api":
            final_prompt = prompt
            if screenplay_mode:
                from services.screenplay_structure import wrap_screenplay_user_prompt

                final_prompt = wrap_screenplay_user_prompt(prompt)
            result_text = await call_openai_compatible(
                model_id=model, prompt=final_prompt, max_tokens=8000
            )
        elif model_type == "local":
            raise ValueError(f"模型 {model} 为本地模型，暂不支持文本 API 调用")
        else:
            raise ValueError(f"模型 {model} 类型不支持: {model_type}")

        task = db.get(Task, task_id)
        if task:
            if task.status == "cancelled":
                return
            _mark_task_terminal(task, status="completed", result=result_text)
        db.commit()
    except Exception as e:
        task = db.get(Task, task_id)
        if task:
            _mark_task_terminal(task, status="failed", error=str(e))
        db.commit()
    finally:
        db.close()


@router.post("/api/tasks/text")
async def canvas_text_task(
    body: CanvasTextRequest,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """画布文本生成：从 registered_models 动态读取模型定义。"""
    check_concurrent_generations(db, user, team_id=body.team_id)
    prompt = body.prompt.strip()
    if not prompt:
        raise HTTPException(status_code=400, detail="请填写文本描述")

    model = body.model.strip()
    row = db.get(RegisteredModel, model)
    if not row:
        raise HTTPException(status_code=400, detail=f"模型不存在: {model}")
    if not row.enabled:
        raise HTTPException(status_code=400, detail=f"模型未启用: {model}")
    if row.category != "text":
        raise HTTPException(status_code=400, detail=f"模型类别不是文本: {model}")

    task_id = str(uuid.uuid4())
    create_task_record(
        db, task_id, "text", "queued",
        user_id=user.id, team_id=body.team_id, prompt_text=prompt,
    )
    db.commit()

    asyncio.create_task(
        _run_text_generation(
            task_id,
            model,
            prompt,
            body.count,
            user.id,
            screenplay_mode=body.screenplay_mode,
        )
    )

    return {"task_id": task_id, "status": "queued"}


# ── Canvas: image generation ──────────────────────────────────────────────────

@router.post("/api/tasks/image")
async def canvas_image_task(
    body: CanvasImageRequest,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """画布图像生成：提交 ComfyUI 工作流并创建 pending 任务供轮询。"""
    studio_print(
        "image",
        f"POST /api/tasks/image 收到 model={body.model} count={body.count} "
        f"ratio={body.ratio} quality={body.quality} node_id={body.node_id}",
    )
    try:
        raw_prompt = body.prompt.strip()
        if not raw_prompt:
            raise HTTPException(status_code=400, detail="请填写画面描述")

        trace_id = str(uuid.uuid4())

        display_for_trace = (body.display_prompt or "").strip() or None
        await push_trace(
            1,
            "SUBMIT",
            {
                "trace_id": trace_id,
                "model": body.model.strip(),
                "prompt": raw_prompt,
                "display_prompt": display_for_trace,
                "denoise": body.denoise,
                "ratio": body.ratio,
                "resolution": body.quality,
                "count": body.count,
            },
        )
        studio_print(
            "trace",
            f"L1 SUBMIT model={body.model} ratio={body.ratio} "
            f"resolution={body.quality} count={body.count}",
        )

        clean_prompt = strip_mention_tokens(raw_prompt)
        mention_ctx = resolve_mentions(db, user.id, body.mentions)
        prompt = enrich_prompt(clean_prompt, mention_ctx.get("context_parts") or [])
        reference_image = body.reference_image
        ref_urls = list(body.reference_images or [])
        mention_ref_urls = mention_ctx.get("reference_image_urls") or []
        for url in mention_ref_urls:
            if url and url not in ref_urls:
                ref_urls.append(url)
        if not reference_image and ref_urls:
            reference_image = ref_urls[0]
        reference_images = list(ref_urls)
        if reference_image and reference_image not in reference_images:
            reference_images.insert(0, reference_image)

        print(
            f"[tasks/image] reference_image={'set' if reference_image else 'none'} "
            f"reference_images count={len(reference_images)}"
        )

        ref_kind = "none"
        if reference_image:
            if reference_image.startswith("data:"):
                ref_kind = "data_url"
            elif reference_image.startswith("blob:"):
                ref_kind = "blob_url"
            elif reference_image.startswith("http"):
                ref_kind = "http_url"
            else:
                ref_kind = "path"
        logger.info(
            "canvas_image_task reference: kind=%s len=%s count=%s",
            ref_kind,
            len(reference_image or ""),
            len(reference_images),
        )

        model_key = body.model.strip()
        width, height = resolve_canvas_image_dimensions(
            model_key, body.ratio, body.quality
        )

        row = db.get(RegisteredModel, model_key)
        if not row:
            raise HTTPException(status_code=400, detail=f"模型不存在: {body.model}")
        if not row.enabled:
            raise HTTPException(status_code=400, detail=f"模型未启用: {body.model}")
        if row.category != "image":
            raise HTTPException(status_code=400, detail=f"模型类别不是图像: {body.model}")
        model_filename = (row.comfyui_file or "").strip()
        if not model_filename:
            raise HTTPException(
                status_code=400,
                detail=f"模型未配置 ComfyUI 权重文件: {body.model}",
            )

        batch_count = max(1, min(int(body.count or 1), 4))

        _release_stale_node_tasks(db, body.node_id, user.id)
        await reconcile_active_tasks_from_comfyui(db, user.id)
        check_concurrent_generations(db, user, slots_needed=batch_count, team_id=body.team_id)
        try:
            check_and_consume(db, user.id, "image")
        except QuotaExceededError as e:
            _release_acquired_slots(user.id, team_id=body.team_id, slots=batch_count)
            raise HTTPException(status_code=429, detail=e.message) from e

        await push_trace(
            2,
            "RECEIVED",
            {
                "trace_id": trace_id,
                "model": body.model.strip(),
                "prompt": prompt,
                "ratio": body.ratio,
                "count": batch_count,
            },
        )
        studio_print(
            "trace",
            f"L2 RECEIVED trace_id={trace_id} model={body.model} prompt_len={len(prompt)} count={batch_count}",
        )

        prompt_before_optimize = prompt
        negative_in = (body.negative_prompt or "").strip()
        positive, negative_opt, optimized, translate_note = await maybe_optimize_prompt(
            prompt, negative_in, "image", True
        )
        if negative_in:
            negative_opt = _merge_negative_prompt(negative_in, negative_opt or "")
        prompt_for_comfy = positive
        l3_trace = {
            "trace_id": trace_id,
            "before": prompt_before_optimize,
            "after": positive,
            "optimized": optimized,
        }
        if not optimized and prompt_before_optimize.strip() == positive.strip():
            l3_trace["optimize_note"] = translate_note or (
                "未翻译：请配置 DASHSCOPE_API_KEY 或启用文本模型以翻译中文"
            )
        await push_trace(3, "TRANSLATED", l3_trace)
        studio_print(
            "trace",
            f"L3 TRANSLATED trace_id={trace_id} optimized={optimized} "
            f"before_len={len(prompt_before_optimize)} after_len={len(positive)}",
        )

        logger.info(
            "canvas_image_task received: model=%s count=%s ratio=%s quality=%s "
            "node_id=%s prompt_len=%s reference_image=%s reference_count=%s mentions=%s",
            body.model,
            body.count,
            body.ratio,
            body.quality,
            body.node_id,
            len(prompt),
            bool(reference_image),
            len(reference_images),
            len(body.mentions or []),
        )
        logger.info(
            "canvas_image_task resolved: batch_count=%s width=%s height=%s model_file=%s",
            batch_count,
            width,
            height,
            model_filename,
        )

        if settings.agent_mock_generation:
            # MOCK PROVIDER — 移除时机：ComfyUI 真实模型接入后
            task_ids: list[str] = []
            for _ in range(batch_count):
                task_id = str(uuid.uuid4())
                create_task_record(
                    db,
                    task_id,
                    "image",
                    "pending",
                    user_id=user.id,
                    team_id=body.team_id,
                    prompt_text=prompt,
                    comfyui_prompt_id=mock_generation.MOCK_PROMPT_ID,
                    node_id=body.node_id,
                )
                task_ids.append(task_id)
            db.commit()
            await push_trace(
                4,
                "WORKFLOW",
                {
                    "trace_id": trace_id,
                    "workflow_mode": "mock",
                    "reference_count": len(reference_images),
                },
            )
            studio_print("image", f"mock 模式提交 task_ids={task_ids}")
            for task_id in task_ids:
                asyncio.create_task(
                    mock_generation.run_mock_image_task(
                        task_id,
                        reference_images,
                        settings.agent_mock_failure_rate,
                    )
                )
            return {"task_ids": task_ids, "task_id": task_ids[0]}

        task_ids: list[str] = []

        for batch_index in range(batch_count):
            studio_print(
                "image",
                f"ComfyUI 提交前 batch={batch_index + 1}/{batch_count} "
                f"model={model_filename} size={width}x{height} ratio={body.ratio} quality={body.quality}",
            )
            try:
                prompt_id, trace_meta = await comfyui_image.submit_image_prompt(
                    prompt_for_comfy,
                    model_filename,
                    width,
                    height,
                    reference_image,
                    reference_images,
                    model_key,
                    skip_translate=optimized or not re.search(r"[\u4e00-\u9fff]", prompt_for_comfy or ""),
                    denoise=body.denoise,
                    negative_prompt=negative_opt or None,
                    db=db,
                    user=user,
                )
                if batch_index == 0:
                    await push_trace(4, "WORKFLOW", {
                        "trace_id": trace_id,
                        **trace_meta["workflow"],
                        "reference_count": trace_meta["workflow"].get("reference_count", 0),
                        "workflow_mode": trace_meta["workflow"].get("workflow_mode", "txt2img"),
                    })
                    studio_print("trace", f"L4 WORKFLOW trace_id={trace_id} {trace_meta['workflow']}")
                studio_print(
                    "image",
                    f"comfyui.submit_image_prompt 返回 prompt_id={prompt_id}",
                )
            except Exception as exc:
                studio_print("image", f"ComfyUI 提交失败: {exc}")
                logger.exception("canvas_image_task comfyui submit failed")
                _release_acquired_slots(
                    user.id,
                    team_id=body.team_id,
                    slots=max(0, batch_count - len(task_ids)),
                )
                raise
            task_id = str(uuid.uuid4())
            studio_print(
                "image",
                f"任务入库 task_id={task_id} comfy_prompt_id={prompt_id}",
            )
            create_task_record(
                db,
                task_id,
                "image",
                "pending",
                user_id=user.id,
                team_id=body.team_id,
                prompt_text=prompt,
                comfyui_prompt_id=prompt_id,
                node_id=body.node_id,
            )
            task_ids.append(task_id)

        db.commit()
        studio_print("image", f"响应 task_ids={task_ids}")

        return {"task_ids": task_ids, "task_id": task_ids[0]}
    except HTTPException:
        raise
    except Exception as e:
        db.rollback()
        print(f"[tasks/image ERROR] {e}")
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=str(e)) from e


async def _image_url_to_base64(
    image_url: str,
    *,
    db: Session,
    user: User,
) -> str:
    """将画布参考图 URL / 本地路径转为 base64，供 ComfyUI 图生视频上传。"""
    if image_url.startswith("http://") or image_url.startswith("https://"):
        async with httpx.AsyncClient(timeout=30.0) as client:
            res = await client.get(image_url)
            res.raise_for_status()
            if len(res.content) > 10 * 1024 * 1024:
                raise ValueError("参考图过大（最大 10MB）")
            data = res.content
    else:
        from services.media_access import assert_user_can_read_upload_url

        path = assert_user_can_read_upload_url(db, user, image_url)
        data = path.read_bytes()
    return base64.b64encode(data).decode("ascii")


# ── Canvas: video generation ──────────────────────────────────────────────────

@router.post("/api/tasks/video")
async def canvas_video_task(
    body: CanvasVideoRequest,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """画布视频生成卡片接口。
    将 ratio + resolution 通过 RESOLUTION_MAP 转为像素宽高；
    duration 和 audio 透传给模型调用函数；
    按 model 分派到 call_wan / call_ltx / call_hunyuan。
    返回 task_id 供前端轮询/WebSocket 回填结果。
    """
    raw_prompt = body.prompt.strip()
    if not raw_prompt:
        raise HTTPException(status_code=400, detail="请填写画面描述")

    await push_trace(
        1,
        "SUBMIT",
        {
            "model": body.model.strip(),
            "prompt": raw_prompt,
            "ratio": body.ratio,
            "resolution": body.resolution,
            "count": body.count,
        },
    )
    studio_print(
        "trace",
        f"L1 SUBMIT model={body.model} ratio={body.ratio} "
        f"resolution={body.resolution} count={body.count}",
    )

    clean_prompt = strip_mention_tokens(raw_prompt)
    mention_ctx = resolve_mentions(db, user.id, body.mentions)
    prompt = enrich_prompt(clean_prompt, mention_ctx.get("context_parts") or [])
    mention_ref_urls = mention_ctx.get("reference_image_urls") or []

    reference_image = body.reference_image
    reference_images = list(body.reference_images or [])
    first_frame = body.first_frame
    last_frame = body.last_frame

    for url in mention_ref_urls:
        if url not in reference_images:
            reference_images.append(url)
        if not first_frame:
            first_frame = url
        if not reference_image:
            reference_image = url

    logger.info(
        "canvas_video_task received: model=%s count=%s generation_mode=%s "
        "ratio=%s resolution=%s duration=%s audio=%s node_id=%s prompt_len=%s "
        "reference_image=%s first_frame=%s last_frame=%s reference_images=%s mentions=%s",
        body.model,
        body.count,
        body.generation_mode,
        body.ratio,
        body.resolution,
        body.duration,
        body.audio,
        body.node_id,
        len(prompt),
        reference_image,
        first_frame,
        last_frame,
        reference_images,
        len(body.mentions or []),
    )

    model_entry = MODEL_MAP.get(body.model.strip()) or MODEL_MAP.get(body.model.strip().lower())
    allowed_durations = (model_entry or {}).get("capabilities", {}).get("durations")
    if not isinstance(allowed_durations, list) or not allowed_durations:
        allowed_durations = [5, 10, 15]
    allowed_durations = [int(d) for d in allowed_durations]
    if body.duration not in allowed_durations:
        opts = " / ".join(str(d) for d in allowed_durations)
        raise HTTPException(
            status_code=400,
            detail=f"视频时长仅支持 {opts} 秒",
        )

    # 解析分辨率
    res_key = (body.ratio, body.resolution)
    if res_key not in RESOLUTION_MAP:
        raise HTTPException(
            status_code=400,
            detail=f"不支持的比例/清晰度组合: {body.ratio} · {body.resolution}",
        )
    width, height = RESOLUTION_MAP[res_key]
    video_backend = resolve_video_backend(body.model.strip())
    if video_backend == "ltx":
        aligned_w, aligned_h = comfyui.align_ltx_dimensions(width, height)
    else:
        aligned_w, aligned_h = comfyui.align_video_dimensions(width, height)
    logger.info(
        "canvas_video_task resolved: ratio=%s resolution=%s map=%sx%s aligned=%sx%s ref=%s backend=%s",
        body.ratio,
        body.resolution,
        width,
        height,
        aligned_w,
        aligned_h,
        bool(body.first_frame or body.reference_image or body.reference_images),
        video_backend,
    )
    studio_print(
        "video",
        f"分辨率映射 {body.ratio}+{body.resolution} → {width}x{height} "
        f"(对齐后 {aligned_w}x{aligned_h}, backend={video_backend})",
    )

    batch_count = max(1, min(int(body.count or 1), 4))
    _release_stale_node_tasks(db, body.node_id, user.id)
    await reconcile_active_tasks_from_comfyui(db, user.id)
    check_concurrent_generations(db, user, slots_needed=batch_count, team_id=body.team_id)
    await push_trace(
        2,
        "RECEIVED",
        {
            "model": body.model.strip(),
            "prompt": prompt,
            "ratio": body.ratio,
            "count": batch_count,
        },
    )
    studio_print(
        "trace",
        f"L2 RECEIVED model={body.model} prompt_len={len(prompt)} count={batch_count}",
    )
    try:
        check_and_consume(db, user.id, "video")
    except QuotaExceededError as e:
        _release_acquired_slots(user.id, team_id=body.team_id, slots=batch_count)
        raise HTTPException(status_code=429, detail=e.message) from e

    prompt_before_optimize = prompt
    positive, negative, optimized, translate_note = await maybe_optimize_prompt(
        prompt, "", "video", True
    )
    l3_trace = {
        "before": prompt_before_optimize,
        "after": positive,
        "optimized": optimized,
    }
    if not optimized and prompt_before_optimize.strip() == positive.strip():
        l3_trace["optimize_note"] = translate_note or (
            "未翻译：请配置 DASHSCOPE_API_KEY 或启用文本模型以翻译中文"
        )
    await push_trace(3, "TRANSLATED", l3_trace)
    studio_print(
        "trace",
        f"L3 TRANSLATED optimized={optimized} before_len={len(prompt_before_optimize)} "
        f"after_len={len(positive)}",
    )

    ref_image = body.first_frame or body.reference_image
    if not ref_image and body.reference_images:
        ref_image = body.reference_images[0]

    mode = "image2video" if ref_image else "text2video"
    image_b64 = None
    if ref_image:
        try:
            image_b64 = await _image_url_to_base64(ref_image, db=db, user=user)
        except ValueError as e:
            raise HTTPException(status_code=400, detail=str(e)) from e

    logger.info(
        "canvas_video_task before comfyui: mode=%s duration=%s optimized=%s",
        mode,
        body.duration,
        optimized,
    )

    studio_print(
        "video",
        f"ComfyUI 提交前 size={width}x{height} ratio={body.ratio} "
        f"resolution={body.resolution} duration={body.duration}s mode={mode} "
        f"generation_mode={body.generation_mode}",
    )

    if settings.agent_mock_generation:
        # MOCK PROVIDER — 移除时机：ComfyUI 真实模型接入后
        task_id = str(uuid.uuid4())
        create_task_record(
            db,
            task_id,
            "video",
            "pending",
            user_id=user.id,
            team_id=body.team_id,
            prompt_text=prompt,
            comfyui_prompt_id=mock_generation.MOCK_PROMPT_ID,
            node_id=body.node_id,
        )
        db.commit()
        tasks_cache.invalidate_tasks_cache()
        asyncio.create_task(
            mock_generation.run_mock_video_task(
                task_id,
                settings.agent_mock_failure_rate,
            )
        )
        studio_print("video", f"mock 模式提交 task_id={task_id}")
        return {
            "task_id": task_id,
            "comfy_prompt_id": mock_generation.MOCK_PROMPT_ID,
            "status": "pending",
        }

    try:
        model_ckpt = (model_entry or {}).get("comfyui_model_file")
        if video_backend == "ltx":
            # 以启动时从 ComfyUI 扫描到的权重为准，避免注册表占位名与磁盘不一致
            model_ckpt = comfyui.LTX_CKPT or model_ckpt
        video_submit_kwargs = dict(
            prompt=positive,
            negative_prompt=negative,
            duration=body.duration,
            width=aligned_w,
            height=aligned_h,
            mode=mode,
            image_b64=image_b64,
            raw_prompt=optimized,
            client_id=body.client_id,
            model_filename=model_ckpt,
        )
        if video_backend == "wan":
            comfy_prompt_id, _client_id, workflow = await comfyui.submit_wan_video_prompt(
                **video_submit_kwargs
            )
            trace_ckpt = model_ckpt or comfyui.WAN_CKPT
        elif video_backend == "hunyuan":
            comfy_prompt_id, _client_id, workflow = await comfyui.submit_hunyuan_video_prompt(
                **video_submit_kwargs
            )
            trace_ckpt = model_ckpt or comfyui.HUNYUAN_CKPT
        else:
            comfy_prompt_id, _client_id, workflow = await comfyui.submit_video_prompt(
                **video_submit_kwargs
            )
            trace_ckpt = comfyui.LTX_CKPT
        workflow_trace = extract_workflow_trace(workflow, trace_ckpt)
        await push_trace(4, "WORKFLOW", workflow_trace)
        studio_print("trace", f"L4 WORKFLOW {workflow_trace}")
    except ValueError as e:
        db.rollback()
        _release_acquired_slots(user.id, team_id=body.team_id, slots=batch_count)
        raise HTTPException(status_code=400, detail=str(e)) from e
    except httpx.ConnectError:
        db.rollback()
        _release_acquired_slots(user.id, team_id=body.team_id, slots=batch_count)
        raise HTTPException(
            status_code=503,
            detail="ComfyUI 服务未启动，请先启动 ComfyUI（端口 8000）",
        )
    except httpx.HTTPStatusError as e:
        db.rollback()
        _release_acquired_slots(user.id, team_id=body.team_id, slots=batch_count)
        raise HTTPException(
            status_code=502,
            detail=f"ComfyUI 返回错误: {e.response.status_code}",
        ) from e
    except Exception as e:
        db.rollback()
        _release_acquired_slots(user.id, team_id=body.team_id, slots=batch_count)
        raise HTTPException(status_code=500, detail=f"提交失败: {e}") from e

    task_id = str(uuid.uuid4())
    create_task_record(
        db,
        task_id,
        "video",
        "pending",
        user_id=user.id,
        team_id=body.team_id,
        prompt_text=prompt,
        comfyui_prompt_id=comfy_prompt_id,
        node_id=body.node_id,
    )
    db.commit()
    tasks_cache.invalidate_tasks_cache()

    studio_print(
        "video",
        f"已入库 task_id={task_id} comfy_prompt_id={comfy_prompt_id} "
        f"轮询请 GET /api/tasks/{task_id}",
    )

    return {
        "task_id": task_id,
        "comfy_prompt_id": comfy_prompt_id,
        "status": "pending",
    }


# ── Canvas: video enhance ─────────────────────────────────────────────────────


@router.post(
    "/api/tasks/video-enhance/recommend-params",
    response_model=VideoEnhanceRecommendResponse,
)
async def canvas_video_enhance_recommend_params(
    body: VideoEnhanceRecommendRequest,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """分析视频属性并推荐画质增强参数（智能模式）。"""
    video_url = (body.video_url or "").strip()
    if not video_url:
        raise HTTPException(status_code=400, detail="视频地址不能为空")

    from services.media_access import resolve_video_source_for_enhance
    from services.video_enhance_probe import probe_video_info_from_url
    from services.video_enhance_recommend import recommend_enhance_params

    try:
        resolve_video_source_for_enhance(db, user, video_url)
    except HTTPException as e:
        raise e
    except Exception as e:
        raise HTTPException(status_code=400, detail="视频源无效或无权访问") from e

    try:
        video_info = await probe_video_info_from_url(db, user, video_url)
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=400, detail="无法分析视频属性") from e

    content_style = "photorealistic_cinema"
    if body.project_id:
        from services.canvas_access import get_accessible_project
        from services.canvas_style_ref import (
            get_script_table_content_style,
            load_canvas_data,
        )

        project = get_accessible_project(db, user, body.project_id)
        if project:
            canvas_data = load_canvas_data(project)
            content_style = get_script_table_content_style(
                canvas_data, body.script_table_node_id
            )

    use_llm = not settings.agent_mock_generation
    params, reasoning = await recommend_enhance_params(
        video_info,
        use_llm=use_llm,
        content_style=content_style,
    )
    return VideoEnhanceRecommendResponse(params=params, reasoning=reasoning)


@router.post("/api/tasks/video-enhance")
async def canvas_video_enhance_task(
    body: VideoEnhanceRequest,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """画布视频画质增强后处理（SeedVR2 优先，Real-ESRGAN fallback）。"""
    video_url = (body.video_url or "").strip()
    if not video_url:
        raise HTTPException(status_code=400, detail="视频地址不能为空")

    from services.media_access import resolve_video_source_for_enhance

    try:
        resolve_video_source_for_enhance(db, user, video_url)
    except HTTPException as e:
        raise e
    except Exception as e:
        raise HTTPException(status_code=400, detail="视频源无效或无权访问") from e

    upscale_factor = body.upscale_factor
    if upscale_factor not in (1.0, 1.5, 2.0, 3.0):
        raise HTTPException(
            status_code=400,
            detail="超分倍数仅支持 1.0 / 1.5 / 2.0 / 3.0",
        )

    if body.batch_size not in (4, 8, 16):
        raise HTTPException(status_code=400, detail="时序批次仅支持 4 / 8 / 16")

    from services.video_enhance_recommend import normalize_enhance_params

    seedvr2_params = normalize_enhance_params(
        {
            "upscale_factor": upscale_factor,
            "strength": body.strength,
            "input_noise_scale": body.input_noise_scale,
            "batch_size": body.batch_size,
            "color_correction": body.color_correction,
            "model_size": body.model_size,
        }
    )
    upscale_factor = seedvr2_params["upscale_factor"]

    resolved = None if settings.agent_mock_generation else resolve_video_enhance_workflow(
        body.workflow
    )
    if not settings.agent_mock_generation and resolved is None:
        raise HTTPException(
            status_code=503,
            detail="当前环境不支持画质增强",
        )

    _release_stale_node_tasks(db, body.node_id, user.id)
    await reconcile_active_tasks_from_comfyui(db, user.id)
    check_concurrent_generations(db, user, slots_needed=1, team_id=body.team_id)

    try:
        check_and_consume(db, user.id, "video")
    except QuotaExceededError as e:
        _release_acquired_slots(user.id, team_id=body.team_id, slots=1)
        raise HTTPException(status_code=429, detail=e.message) from e

    prompt_label = f"video_enhance x{upscale_factor} {body.strength}"

    if settings.agent_mock_generation:
        task_id = str(uuid.uuid4())
        create_task_record(
            db,
            task_id,
            "video_enhance",
            "pending",
            user_id=user.id,
            team_id=body.team_id,
            prompt_text=prompt_label,
            comfyui_prompt_id=mock_generation.MOCK_PROMPT_ID,
            node_id=body.node_id,
        )
        db.commit()
        tasks_cache.invalidate_tasks_cache()
        asyncio.create_task(
            mock_generation.run_mock_video_enhance_task(
                task_id,
                video_url,
                settings.agent_mock_failure_rate,
            )
        )
        studio_print("video-enhance", f"mock 模式提交 task_id={task_id}")
        return {
            "task_id": task_id,
            "comfy_prompt_id": mock_generation.MOCK_PROMPT_ID,
            "status": "pending",
        }

    provider_id, _provider = resolved
    try:
        if provider_id == VIDEO_ENHANCE_SEEDVR2_ID:
            comfy_prompt_id, _client_id, workflow = await comfyui.submit_seedvr2_enhance_prompt(
                video_url,
                db=db,
                user=user,
                upscale_factor=upscale_factor,
                strength=seedvr2_params["strength"],
                input_noise_scale=seedvr2_params["input_noise_scale"],
                batch_size=seedvr2_params["batch_size"],
                color_correction=seedvr2_params["color_correction"],
                model_size=seedvr2_params["model_size"],
                client_id=body.client_id,
            )
        else:
            comfy_prompt_id, _client_id, workflow = await comfyui.submit_realesrgan_enhance_prompt(
                video_url,
                db=db,
                user=user,
                upscale_factor=upscale_factor,
                client_id=body.client_id,
            )
        workflow_trace = extract_workflow_trace(workflow, provider_id)
        await push_trace(4, "WORKFLOW", workflow_trace)
        studio_print("trace", f"L4 WORKFLOW video-enhance {workflow_trace}")
    except ValueError as e:
        db.rollback()
        _release_acquired_slots(user.id, team_id=body.team_id, slots=1)
        from comfyui.client import map_enhance_submit_error

        raise HTTPException(status_code=400, detail=map_enhance_submit_error(str(e))) from e
    except httpx.ConnectError:
        db.rollback()
        _release_acquired_slots(user.id, team_id=body.team_id, slots=1)
        raise HTTPException(
            status_code=503,
            detail="ComfyUI 服务未启动，请先启动 ComfyUI",
        )
    except httpx.HTTPStatusError as e:
        db.rollback()
        _release_acquired_slots(user.id, team_id=body.team_id, slots=1)
        raise HTTPException(
            status_code=502,
            detail=f"ComfyUI 返回错误: {e.response.status_code}",
        ) from e
    except Exception as e:
        db.rollback()
        _release_acquired_slots(user.id, team_id=body.team_id, slots=1)
        raise HTTPException(status_code=500, detail=f"提交失败: {e}") from e

    task_id = str(uuid.uuid4())
    create_task_record(
        db,
        task_id,
        "video_enhance",
        "pending",
        user_id=user.id,
        team_id=body.team_id,
        prompt_text=prompt_label,
        comfyui_prompt_id=comfy_prompt_id,
        node_id=body.node_id,
    )
    db.commit()
    tasks_cache.invalidate_tasks_cache()

    studio_print(
        "video-enhance",
        f"已入库 task_id={task_id} provider={provider_id} comfy_prompt_id={comfy_prompt_id}",
    )

    return {
        "task_id": task_id,
        "comfy_prompt_id": comfy_prompt_id,
        "status": "pending",
    }


@router.post("/api/tasks/video-lut")
async def canvas_video_lut_task(
    body: VideoLutRequest,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """视频 LUT 后处理（ffmpeg lut3d）。"""
    from services.canvas_access import get_accessible_project
    from services.canvas_style_ref import load_canvas_data
    from services.lut_canvas import lut_is_configured, resolve_active_lut_from_table
    from services.lut_task_service import queue_video_lut_task

    project = get_accessible_project(db, user, body.project_id, require_edit=True)
    canvas_data = load_canvas_data(project)
    if not lut_is_configured(canvas_data, body.script_table_node_id):
        raise HTTPException(status_code=400, detail="项目未配置 LUT")

    lut_preset, lut_custom_url = resolve_active_lut_from_table(
        canvas_data, body.script_table_node_id
    )
    task_id = await queue_video_lut_task(
        db=db,
        user=user,
        video_url=body.video_url,
        node_id=body.node_id,
        project_id=body.project_id,
        script_table_node_id=body.script_table_node_id,
        lut_preset=lut_preset,
        lut_custom_url=lut_custom_url,
        team_id=body.team_id,
    )
    if not task_id:
        raise HTTPException(status_code=400, detail="无法创建 LUT 任务")
    return {"task_id": task_id, "status": "pending"}
