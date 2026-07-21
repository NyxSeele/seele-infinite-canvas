import asyncio
import base64
import json
import logging
import re
import traceback
import uuid
from datetime import datetime, timezone
from pathlib import Path

import httpx
from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import Field
from sqlalchemy.orm import Session

from comfyui import client as comfyui
from core.config import settings
from core.datetime_utils import to_utc_iso
from db.session import get_db
from core.dependencies import get_current_user
from models import RegisteredModel, Task, User
from models.team import Team
from services.task_state import (
    SEEDANCE_PENDING_IDS,
    comfy_id_counts_as_executed,
    is_comfy_cancellable_prompt_id,
    reload_task_if_active,
    task_is_writable,
)
from services.video_postprocess import schedule_video_postprocess
from services.video_faststart import schedule_video_faststart
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
    ImageEnhanceRequest,
    VideoLutRequest,
    TaskRatingRequest,
)
from services.generation_guard import (
    check_concurrent_generations,
    reconcile_active_tasks_from_comfyui,
)
from services.media_access import append_media_ticket, grant_output_access, issue_media_ticket
from services.prompt import (
    PromptTranslationError,
    apply_video_anatomy_guard,
    maybe_optimize_prompt,
    resolve_video_sampling_profile,
)
from services.prompt_builder import (
    apply_flux_positive_suffixes,
    apply_qwen_image_suffixes,
    build_ltx2_prompt,
    build_ltx23_prompt,
    build_wan_prompt,
    is_flux_workflow_type,
    merge_ltx2_negative,
    merge_ltx23_negative,
    merge_wan_negative,
)
from services.quota_service import (
    QuotaExceededError,
    check_and_consume,
    create_task_record,
    refund_quota,
)
from model_registry import (
    MODEL_MAP,
    get_video_allowed_resolutions,
    resolve_generation_profile,
    resolve_image_dimensions_for_model,
    resolve_video_backend,
    resolve_video_enhance_workflow,
    VIDEO_ENHANCE_REALESRGAN_ID,
    VIDEO_ENHANCE_SEEDVR2_ID,
    IMAGE_ENHANCE_SEEDVR2_ID,
)
from services import mock_generation


class CanvasVideoRequestExt(CanvasVideoRequest):
    audio_url: str | None = Field(
        default=None,
        description="参考音频 URL（ltx23-i2av 可选，/api/uploads/audio/...）",
    )
from services import tasks_cache
from services.mention_context import enrich_prompt, resolve_mentions, strip_mention_tokens
from services.quality_presets import get_suffixes, normalize_quality_preset_id
from services.task_generation_params import (
    build_image_generation_params,
    build_video_generation_params,
    parse_generation_params,
)
from core.logging_setup import studio_print
from trace_bus import (
    build_lut_trace,
    build_mock_workflow_trace,
    extract_enhance_trace,
    extract_workflow_trace,
    push_trace,
)


_MEDIA_TASK_TYPES = ("image", "video", "video_enhance", "video_lut")


def _resolve_poll_generation_seconds(
    task: Task,
    *,
    override: float | None = None,
) -> float | None:
    """轮询响应优先用当次 Comfy 查询结果，其次读 task / DB。"""
    if override is not None:
        return override
    return task.generation_seconds


def _with_comfy_prompt_id(
    payload: dict,
    task: Task,
    *,
    generation_seconds: float | None = None,
) -> dict:
    """媒体任务轮询响应附带 comfy_prompt_id，供前端对齐 WS prompt_id。"""
    if task.task_type in _MEDIA_TASK_TYPES:
        payload["comfy_prompt_id"] = task.comfyui_prompt_id
        payload["generation_seconds"] = _resolve_poll_generation_seconds(
            task,
            override=generation_seconds,
        )
        if (
            not task.comfyui_prompt_id
            and task.status in ("pending", "processing")
        ):
            payload.setdefault("stage", "preparing")
            payload.setdefault("message", "preparing")
    return payload


def _release_task_gpu_node(task: Task | None) -> None:
    if not task:
        return
    from services.gpu_pool import release_gpu_node

    release_gpu_node(task.comfyui_node_url)


def _assign_comfy_submission(
    task: Task | None,
    *,
    comfy_prompt_id: str,
    node_url: str | None,
) -> None:
    if not task:
        return
    task.comfyui_prompt_id = comfy_prompt_id
    if node_url:
        task.comfyui_node_url = node_url.rstrip("/")


def _is_deprecated_hunyuan_model(model_id: str | None) -> bool:
    mid = (model_id or "").strip().lower()
    return mid.startswith("hunyuan") or "hunyuanvideo" in mid


def remap_deprecated_video_model(model_id: str, *, mode: str) -> str:
    """已下线 Hunyuan 本地链路：旧画布 JSON 降级到 Wan。"""
    if not _is_deprecated_hunyuan_model(model_id):
        return model_id
    if mode in ("image2video", "flf2v", "fun_inpaint"):
        return "wan-i2v"
    return "wan-2.6"


def estimate_duration(model_id: str, params: dict | None = None) -> int:
    """估算生成耗时（秒），用于 short/long 队列分流。"""
    params = params or {}
    mid = (model_id or "").strip().lower()
    steps = int(params.get("steps") or 0) or None
    duration = int(params.get("duration") or params.get("duration_sec") or 5)
    width = int(params.get("width") or 0)
    height = int(params.get("height") or 0)
    use_distilled = bool(params.get("use_distilled"))
    pixels = max(width, 1) * max(height, 1) if width and height else 0

    if mid in ("flux-dev", "hidream", "flux", "hidream-i1") or mid.startswith("flux") or mid.startswith("hidream"):
        return 30
    if mid in ("video-enhance-seedvr2",) or "seedvr2" in mid:
        return 60
    if mid.startswith("wan") or mid in ("wan-2.6", "wan-i2v", "wan-fun-inpaint"):
        base_steps = steps or 4
        # 轻量估算：时长 × 步数 × 基准
        return max(45, int(duration * max(base_steps, 1) * 2.5))
    if "ltx" in mid:
        return 180
    return 120


def estimate_queue_bucket(model_id: str, params: dict | None = None) -> str:
    from services.gpu_pool import queue_bucket

    return queue_bucket(estimate_duration(model_id, params))


def _merge_negative_prompt(built: str, optimized: str) -> str:
    """保留分镜预构建 negative（含二次元排除项），与 L3 结果合并。"""
    chunks: list[str] = []
    for raw in (optimized, built):
        for part in (raw or "").split(","):
            p = part.strip()
            if p and p not in chunks:
                chunks.append(p)
    return ", ".join(chunks)


async def _translate_for_generation(
    prompt: str,
    negative: str,
    mode: str,
    auto_optimize: bool,
    *,
    model_hint: str | None = None,
) -> tuple[str, str, bool]:
    """生图/生视频前强制英译；失败抛 HTTP 422。"""
    try:
        positive, negative_out, optimized, _ = await maybe_optimize_prompt(
            prompt,
            negative,
            mode,
            auto_optimize,
            model_hint=model_hint,
        )
    except PromptTranslationError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    return positive, negative_out, optimized


def _finalize_image_positive_for_model(
    positive: str,
    *,
    model_key: str,
    model_filename: str,
    quality_preset_id: str = "auto",
) -> str:
    profile = resolve_generation_profile(model_key, model_filename)
    workflow_type = profile.get("workflow_type", "sd15")
    result = positive
    if workflow_type == "qwen-image":
        result = apply_qwen_image_suffixes(result)
    elif is_flux_workflow_type(workflow_type):
        result = apply_flux_positive_suffixes(result)
    pos_suffix, _ = get_suffixes(quality_preset_id)
    if pos_suffix:
        result = f"{result}, {pos_suffix}" if result.strip() else pos_suffix
    return result


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


def _placeholder_task_progress(task: Task) -> int:
    """无 Comfy/外部细粒度进度时的占位值（勿用 50，前端会误以为已完成一半）。"""
    if task.status == "completed":
        return 100
    if task.status in _TERMINAL_TASK_STATUSES:
        return 0
    return 0


def _media_task_poll_response(
    task: Task,
    user: User,
    db: Session | None = None,
    *,
    generation_seconds: float | None = None,
) -> dict:
    """终态或不可再 poll 的任务：直接返回 DB 状态，勿用 Comfy 进度覆盖。"""
    if db is not None:
        db.refresh(task)
    progress = 100 if task.status == "completed" else 0
    result = None
    if task.result:
        result = _sign_result_url_for_user(task.result, user.id)
    return _with_comfy_prompt_id(
        {
            "task_id": task.id,
            "status": task.status,
            "progress": progress,
            "result": result,
            "error": task.error,
        },
        task,
        generation_seconds=generation_seconds,
    )


def _release_stale_node_tasks(
    db: Session,
    node_id: str | None,
    user_id: int,
    *,
    reason: str = "被新任务取代",
) -> list[Task]:
    """将同一画布节点上未结束的任务标为 failed，避免阻塞新提交。"""
    if not node_id:
        return []
    rows = (
        db.query(Task)
        .filter(
            Task.node_id == node_id,
            Task.user_id == user_id,
            Task.status.in_(list(_ACTIVE_TASK_STATUSES)),
        )
        .all()
    )
    return rows


async def _cancel_stale_comfy_tasks(tasks: list[Task]) -> None:
    """释放同节点旧任务时，取消 ComfyUI 队列/执行，避免 GPU 被占而前端像卡住。"""
    seen: set[tuple[str, str]] = set()
    for task in tasks:
        comfy_id = (task.comfyui_prompt_id or "").strip()
        if not is_comfy_cancellable_prompt_id(comfy_id):
            continue
        node_url = (task.comfyui_node_url or "").strip() or None
        key = (comfy_id, node_url or "")
        if key in seen:
            continue
        seen.add(key)
        try:
            await comfyui.cancel_task(comfy_id, node_url=node_url)
        except Exception as exc:
            logger.warning(
                "cancel stale comfy task failed prompt_id=%s node=%s: %s",
                comfy_id,
                node_url,
                exc,
            )
        try:
            await comfyui.interrupt_execution(node_url=node_url)
        except Exception as exc:
            logger.warning(
                "interrupt stale comfy node failed prompt_id=%s node=%s: %s",
                comfy_id,
                node_url,
                exc,
            )


def _mark_stale_node_tasks_terminal(
    db: Session,
    node_id: str | None,
    user_id: int,
    *,
    reason: str = "被新任务取代",
) -> list[Task]:
    """同节点旧任务标为 failed 并立即 commit，避免轮询/worker 竞态写回 running。"""
    rows = _release_stale_node_tasks(db, node_id, user_id, reason=reason)
    if not rows:
        return []
    for task in rows:
        _refund_task_quota_if_not_executed(db, task)
        _mark_task_terminal(task, status="failed", error=reason)
    db.commit()
    logger.info(
        "released %s stale task(s) for node_id=%s user_id=%s",
        len(rows),
        node_id,
        user_id,
    )
    return rows


async def _release_stale_node_tasks_async(
    db: Session,
    node_id: str | None,
    user_id: int,
    *,
    reason: str = "被新任务取代",
) -> int:
    rows = _mark_stale_node_tasks_terminal(db, node_id, user_id, reason=reason)
    if not rows:
        return 0
    await _cancel_stale_comfy_tasks(rows)
    return len(rows)


async def _resolve_image_result_from_history(
    comfy_prompt_id: str,
    user_id: int,
    node_url: str | None = None,
) -> str | None:
    """从 ComfyUI history 解析图片 view URL（与 providers.comfyui 逻辑互补）。"""
    from comfyui.client import _view_url_for_media

    raw = await comfyui_image.get_image_result(comfy_prompt_id, node_url=node_url)
    if isinstance(raw, str) and raw.strip():
        url = _view_url_for_media(
            {"filename": raw.strip(), "type": "output"},
            node_url=node_url,
        )
        return _sign_result_url_for_user(url, user_id)
    return None


def _mark_task_terminal(
    task: Task,
    *,
    status: str,
    error: str | None = None,
    result: str | None = None,
    generation_seconds: float | None = None,
) -> None:
    """写入终态，供轮询与僵尸释放逻辑一致使用。"""
    was_active = task.status in _ACTIVE_TASK_STATUSES
    task.status = status
    task.error = error[:2000] if error else None
    if result is not None:
        task.result = result
    elif status in _TERMINAL_TASK_STATUSES and status != "completed":
        task.result = None
    if status in _TERMINAL_TASK_STATUSES:
        from models.task import utcnow

        task.completed_at = utcnow()
        if generation_seconds is not None:
            task.generation_seconds = generation_seconds
    if was_active and status in _TERMINAL_TASK_STATUSES:
        from services.generation_slots import release_slots

        release_slots(task.user_id, team_id=task.team_id)
    if status in _TERMINAL_TASK_STATUSES:
        _release_task_gpu_node(task)


_MEDIA_QUOTA_REFUND_TYPES = frozenset({"image", "video", "video_enhance", "video_lut"})


def _refund_task_quota_if_not_executed(db: Session, task: Task) -> None:
    """任务从未进入执行时退还配额（与 async 提交失败退还一致）。"""
    if not task or not task.user_id:
        return
    if task.task_type not in _MEDIA_QUOTA_REFUND_TYPES:
        return
    should_refund = False
    quota_kind = "video"
    if task.task_type == "image":
        quota_kind = "image"
        should_refund = not task.comfyui_prompt_id
    elif task.task_type == "video_lut":
        should_refund = not (task.result and str(task.result).strip())
    else:
        should_refund = not comfy_id_counts_as_executed(task)
    if should_refund:
        refund_quota(db, task.user_id, quota_kind, 1)


def _schedule_video_postprocess(task: Task) -> None:
    schedule_video_postprocess(task)


def _schedule_video_faststart(task: Task, result_url: str | None) -> None:
    if task.task_type != "video" or not result_url:
        return
    schedule_video_faststart(task.id, result_url, task.user_id)


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

    from services.prompt import contains_cjk

    if contains_cjk(text):
        positive, negative, _optimized = await _translate_for_generation(
            text, "", mode, True
        )
        return {
            "positive": positive,
            "negative": negative or "worst quality, low quality, blurry",
        }

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
    await check_concurrent_generations(db, user, team_id=body.team_id)
    prompt = body.prompt.strip()
    if not prompt:
        raise HTTPException(status_code=400, detail="请填写画面描述")

    if body.style not in comfyui.STYLE_SUFFIXES:
        raise HTTPException(status_code=400, detail="无效的风格选项")

    try:
        check_and_consume(db, user.id, "image")
    except QuotaExceededError as e:
        raise HTTPException(status_code=429, detail=e.message) from e

    positive, negative, optimized = await _translate_for_generation(
        prompt, body.negative_prompt, "image", body.auto_optimize
    )

    try:
        task_id, client_id, node_url = await comfyui.submit_prompt(
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
        comfyui_node_url=node_url,
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
    await check_concurrent_generations(db, user, team_id=body.team_id)
    prompt = body.prompt.strip()
    if not prompt:
        raise HTTPException(status_code=400, detail="请填写画面描述")

    if body.duration not in (3, 5, 10, 15):
        raise HTTPException(status_code=400, detail="视频时长仅支持 3 / 5 / 10 / 15 秒")

    if body.mode not in ("text2video", "image2video"):
        raise HTTPException(status_code=400, detail="无效的生成模式")

    if body.mode == "image2video" and not body.image:
        raise HTTPException(status_code=400, detail="图生视频需要上传图片")

    width, height = comfyui.align_ltx_dimensions(body.width, body.height)

    try:
        check_and_consume(db, user.id, "video")
    except QuotaExceededError as e:
        raise HTTPException(status_code=429, detail=e.message) from e

    positive, negative, optimized = await _translate_for_generation(
        prompt, body.negative_prompt, "video", body.auto_optimize
    )

    try:
        task_id, client_id, _workflow, node_url = await comfyui.submit_video_prompt(
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
        comfyui_node_url=node_url,
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
    if user.role != "admin" and (task.user_id is None or task.user_id != user.id):
        raise HTTPException(status_code=403, detail="无权访问该任务")

    # JSON async jobs (screenplay / prompt LLM / import LLM / enhance reco / style_ref): no ComfyUI
    if task.task_type in (
        "sp_structure",
        "sp_shots",
        "sp_expand",
        "sp_beats",
        "imp_parse",
        "imp_group",
        "ve_reco",
        "style_ref",
    ):
        progress = (
            100
            if task.status == "completed"
            else (
                50
                if task.status in ("pending", "queued", "processing", "running")
                else 0
            )
        )
        result: object | None = task.result
        if task.status == "completed" and isinstance(result, str) and result:
            try:
                result = json.loads(result)
            except json.JSONDecodeError:
                pass
        return {
            "task_id": task.id,
            "status": task.status,
            "progress": progress,
            "result": result,
            "error": task.error,
        }

    if task.task_type in _MEDIA_TASK_TYPES and task.status == "completed" and task.result:
        schedule_video_postprocess(task)
        db.refresh(task)
        return _with_comfy_prompt_id(
            {
                "task_id": task.id,
                "status": "completed",
                "progress": 100,
                "result": _sign_result_url_for_user(task.result, user.id),
                "error": None,
            },
            task,
        )

    if task.comfyui_prompt_id == mock_generation.MOCK_PROMPT_ID:
        if task.status == "failed":
            return _with_comfy_prompt_id(
                {
                    "task_id": task.id,
                    "status": "failed",
                    "progress": 0,
                    "result": None,
                    "error": task.error,
                },
                task,
            )
        return _with_comfy_prompt_id(
            {
                "task_id": task.id,
                "status": task.status,
                "progress": _placeholder_task_progress(task),
                "result": None,
                "error": None,
            },
            task,
        )

    # Seedance / 外部异步任务：不走 ComfyUI poll，直接读 DB
    if (
        task.task_type == "video"
        and task.comfyui_prompt_id
        and (
            task.comfyui_prompt_id in SEEDANCE_PENDING_IDS
            or str(task.comfyui_prompt_id).startswith("seedance:")
        )
    ):
        progress = _placeholder_task_progress(task)
        return _with_comfy_prompt_id(
            {
                "task_id": task.id,
                "status": task.status,
                "progress": progress,
                "result": _sign_result_url_for_user(task.result, user.id) if task.result else None,
                "error": task.error,
            },
            task,
        )

    # 媒体任务后台提交尚未拿到 Comfy prompt id：勿用 task.id 误查 Comfy
    if task.task_type in _MEDIA_TASK_TYPES and not task.comfyui_prompt_id:
        progress = _placeholder_task_progress(task)
        return _with_comfy_prompt_id(
            {
                "task_id": task.id,
                "status": task.status,
                "progress": progress,
                "result": (
                    _sign_result_url_for_user(task.result, user.id) if task.result else None
                ),
                "error": task.error,
            },
            task,
        )

    comfy_prompt_id = task.comfyui_prompt_id or (
        task.id if task.task_type in _MEDIA_TASK_TYPES else None
    )

    if (
        comfy_prompt_id
        and task.task_type in _MEDIA_TASK_TYPES
        and task.task_type != "video_lut"
    ):
        if task.status in _TERMINAL_TASK_STATUSES:
            return _media_task_poll_response(task, user, db)

        if task.status in ("pending", "queued", "running", "processing"):
            exec_info = await comfyui.get_prompt_execution_status(
                comfy_prompt_id,
                node_url=task.comfyui_node_url,
            )
            exec_generation_seconds = exec_info.get("generation_seconds")
            task = reload_task_if_active(db, task)
            if task is None:
                stale = db.get(Task, task_id)
                if not stale:
                    raise HTTPException(status_code=404, detail="任务不存在")
                if (
                    exec_generation_seconds is not None
                    and stale.generation_seconds is None
                    and stale.status in _TERMINAL_TASK_STATUSES
                ):
                    stale.generation_seconds = exec_generation_seconds
                    db.commit()
                return _media_task_poll_response(
                    stale,
                    user,
                    db,
                    generation_seconds=exec_generation_seconds,
                )

            api_status = exec_info.get("status") or task.status
            progress = int(exec_info.get("progress") or 0)
            studio_print(
                "poll",
                f"GET /api/tasks/{task_id} type={task.task_type} "
                f"comfy_prompt_id={comfy_prompt_id} api_status={api_status} "
                f"progress={progress} has_result={bool(exec_info.get('result'))}",
            )

            if api_status == "completed" and exec_info.get("result"):
                raw_result = exec_info["result"]
                _mark_task_terminal(
                    task,
                    status="completed",
                    result=_sign_result_url_for_user(
                        raw_result,
                        task.user_id or user.id,
                    ),
                    generation_seconds=exec_generation_seconds,
                )
                db.commit()
                studio_print(
                    task.task_type,
                    f"任务完成 task_id={task_id} comfy_prompt_id={comfy_prompt_id} "
                    f"result={task.result}",
                )
                if task.task_type == "video":
                    _schedule_video_faststart(task, raw_result)
                    _schedule_video_postprocess(task)
                return _with_comfy_prompt_id(
                    {
                        "task_id": task.id,
                        "status": "completed",
                        "progress": 100,
                        "result": task.result,
                        "error": None,
                    },
                    task,
                    generation_seconds=exec_generation_seconds,
                )

            if api_status == "failed":
                _mark_task_terminal(
                    task,
                    status="failed",
                    error=exec_info.get("error") or "生成失败",
                    generation_seconds=exec_generation_seconds,
                )
                db.commit()
                studio_print(
                    task.task_type,
                    f"任务失败 task_id={task_id} error={task.error}",
                )
                return _with_comfy_prompt_id(
                    {
                        "task_id": task.id,
                        "status": "failed",
                        "progress": progress,
                        "result": None,
                        "error": task.error,
                    },
                    task,
                    generation_seconds=exec_generation_seconds,
                )

            if api_status == "completed" and not exec_info.get("result"):
                fallback_result = await _resolve_image_result_from_history(
                    comfy_prompt_id,
                    task.user_id or user.id,
                    node_url=task.comfyui_node_url,
                )
                if fallback_result:
                    _mark_task_terminal(
                        task,
                        status="completed",
                        result=fallback_result,
                        generation_seconds=exec_generation_seconds,
                    )
                    db.commit()
                    studio_print(
                        "poll",
                        f"history 回退命中图片 task_id={task_id} result={fallback_result}",
                    )
                    return _with_comfy_prompt_id(
                        {
                            "task_id": task.id,
                            "status": "completed",
                            "progress": 100,
                            "result": task.result,
                            "error": None,
                        },
                        task,
                        generation_seconds=exec_generation_seconds,
                    )
                err = "ComfyUI 已完成但未返回图片 URL"
                _mark_task_terminal(
                    task,
                    status="failed",
                    error=err,
                    generation_seconds=exec_generation_seconds,
                )
                db.commit()
                studio_print("poll", f"任务异常完成无输出 task_id={task_id}")
                return _with_comfy_prompt_id(
                    {
                        "task_id": task.id,
                        "status": "failed",
                        "progress": progress,
                        "result": None,
                        "error": err,
                    },
                    task,
                    generation_seconds=exec_generation_seconds,
                )

            if api_status in ("running", "pending"):
                if task.status != api_status:
                    task.status = api_status
                    db.commit()
                return _with_comfy_prompt_id(
                    {
                        "task_id": task.id,
                        "status": api_status,
                        "progress": progress,
                        "stage": exec_info.get("stage"),
                        "message": exec_info.get("message"),
                        "result": None,
                        "error": None,
                    },
                    task,
                )

    return _with_comfy_prompt_id(
        {
            "task_id": task.id,
            "status": task.status,
            "progress": 0,
            "result": task.result,
            "error": task.error,
        },
        task,
    )


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
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """取消 ComfyUI 队列任务；画布 task_id 会解析为 comfyui_prompt_id。"""
    task = db.get(Task, task_id)
    if not task:
        raise HTTPException(status_code=404, detail="任务不存在")
    if user.role != "admin" and (task.user_id is None or task.user_id != user.id):
        raise HTTPException(status_code=403, detail="无权取消该任务")

    comfy_id = (task.comfyui_prompt_id or "").strip()
    if task.status not in ("completed", "failed", "cancelled"):
        _mark_task_terminal(
            task,
            status="cancelled",
            error="用户已停止生成",
        )
        _refund_task_quota_if_not_executed(db, task)
        db.commit()
    if is_comfy_cancellable_prompt_id(comfy_id):
        node_url = (task.comfyui_node_url or "").strip() or None
        try:
            await comfyui.cancel_task(comfy_id, node_url=node_url)
        except httpx.HTTPStatusError as e:
            raise HTTPException(
                status_code=502,
                detail=f"取消失败: {e.response.text}",
            ) from e
        except Exception as e:
            raise HTTPException(status_code=500, detail=f"取消失败: {e}") from e
        # 队列 delete 无法终止已在 GPU 上执行的 workflow，须额外 interrupt
        try:
            await comfyui.interrupt_execution(node_url=node_url)
        except Exception as exc:
            logger.warning(
                "interrupt comfy after user cancel failed task=%s prompt=%s node=%s: %s",
                task_id,
                comfy_id,
                node_url,
                exc,
            )

    tasks_cache.invalidate_tasks_cache()
    return {"message": "已取消", "task_id": task_id}


@router.post("/api/tasks/{task_id}/rating")
async def submit_task_rating(
    task_id: str,
    body: TaskRatingRequest,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """提交生成任务满意度评价。"""
    if body.rating not in (0, 1):
        raise HTTPException(status_code=400, detail="rating 只能是 0 或 1")

    task = db.get(Task, task_id)
    if not task:
        raise HTTPException(status_code=404, detail="任务不存在")
    if user.role != "admin" and (task.user_id is None or task.user_id != user.id):
        raise HTTPException(status_code=403, detail="无权评价该任务")

    if body.rating == 0:
        tags = [t.strip() for t in (body.tags or []) if t and str(t).strip()]
        if not tags:
            raise HTTPException(status_code=400, detail="不满意时请至少选择一个原因标签")
        comment = (body.comment or "").strip()
        if "其他" in tags and not comment:
            raise HTTPException(status_code=400, detail="选择「其他」时请填写简短说明（1-200字）")
        if comment and len(comment) > 200:
            raise HTTPException(status_code=400, detail="补充说明不能超过200字")
    else:
        tags = []
        comment = None

    task.user_rating = body.rating
    task.rating_tags = json.dumps(tags, ensure_ascii=False) if body.rating == 0 else None
    task.rating_comment = comment if body.rating == 0 else None
    task.rated_at = datetime.now(timezone.utc)

    params = parse_generation_params(task.generation_params)
    project_id = (params.get("project_id") or "").strip()
    if project_id and task.model_id:
        try:
            from services.canvas_access import get_accessible_project
            from services.generation_memory_service import record_feedback_routing_hint

            project = get_accessible_project(db, user, project_id)
            record_feedback_routing_hint(
                project,
                model_id=task.model_id,
                rating=body.rating,
            )
        except HTTPException:
            pass
        except Exception:
            logger.exception("record_feedback_routing_hint failed task_id=%s", task_id)

    db.commit()
    return {"ok": True}


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
    ("16:9", "480P"):  (854, 480),
    ("9:16", "480P"):  (480, 854),
    ("1:1",  "480P"):  (480, 480),
    ("16:9", "720P"):  (1280, 720),
    ("9:16", "720P"):  (720, 1280),
    ("1:1",  "720P"):  (720, 720),
    ("16:9", "1080P"): (1920, 1080),
    ("9:16", "1080P"): (1080, 1920),
    ("1:1",  "1080P"): (1080, 1080),
})

def resolve_canvas_image_dimensions(
    model_id: str,
    ratio: str,
    quality: str | None,
    width: int | None = None,
    height: int | None = None,
) -> tuple[int, int]:
    """画布图像：按模型 recommended_resolutions / 显式宽高解析。"""
    try:
        return resolve_image_dimensions_for_model(
            model_id, ratio, quality, width=width, height=height
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e


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
            mode = "screenplay" if screenplay_mode else "chat"
            input_len = len(final_prompt)
            studio_print("trace", f"A2 TEXT_INPUT mode={mode} input_len={input_len}")
            result_text = await call_openai_compatible(
                model_id=model, prompt=final_prompt, max_tokens=8000
            )
            studio_print(
                "trace",
                f"A2 TEXT_OUTPUT mode={mode} output_len={len(result_text or '')}",
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
    await check_concurrent_generations(db, user, team_id=body.team_id)
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
        model_id=model,
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


async def _run_canvas_image_submit_task(
    task_ids: list[str],
    *,
    user_id: int,
    team_id: str | None,
    prompt: str,
    negative_in: str,
    reference_image: str | None,
    reference_images: list[str],
    model_key: str,
    model_filename: str,
    width: int,
    height: int,
    denoise: float,
    use_reactor: bool,
    ratio: str,
    quality: str,
    trace_id: str,
    quality_preset_id: str = "auto",
) -> None:
    """后台：optimize + Comfy 提交，写回各 image 任务的 comfyui_prompt_id。"""
    from db.session import SessionLocal

    db = SessionLocal()
    batch_count = len(task_ids)
    try:
        user = db.get(User, user_id)
        if not user:
            raise ValueError("用户不存在")

        for tid in task_ids:
            task = db.get(Task, tid)
            if task and task.status != "cancelled":
                task.status = "processing"
                task.error = None
        db.commit()

        prompt_before_optimize = prompt
        try:
            positive, negative_opt, optimized = await _translate_for_generation(
                prompt, negative_in, "image", True, model_hint=model_key
            )
        except HTTPException as exc:
            err = str(exc.detail)
            for tid in task_ids:
                fail_task = db.get(Task, tid)
                if fail_task and fail_task.status not in (
                    "completed",
                    "failed",
                    "cancelled",
                ):
                    _mark_task_terminal(fail_task, status="failed", error=err)
            refund_quota(db, user_id, "image", batch_count)
            db.commit()
            tasks_cache.invalidate_tasks_cache()
            await push_trace(
                3,
                "TRANSLATED",
                {
                    "trace_id": trace_id,
                    "before": prompt_before_optimize,
                    "after": prompt_before_optimize,
                    "optimized": False,
                    "optimize_note": err,
                },
            )
            return
        prompt_for_comfy = _finalize_image_positive_for_model(
            positive,
            model_key=model_key,
            model_filename=model_filename,
            quality_preset_id=quality_preset_id,
        )
        l3_trace = {
            "trace_id": trace_id,
            "before": prompt_before_optimize,
            "after": positive,
            "after_final": prompt_for_comfy,
            "optimized": optimized,
            "negative_before": negative_in or None,
            "negative_after": negative_opt or None,
        }
        await push_trace(3, "TRANSLATED", l3_trace)

        for tid in task_ids:
            trace_task = db.get(Task, tid)
            if trace_task and trace_task.status != "cancelled":
                trace_task.compiled_prompt = prompt_for_comfy
        db.commit()

        submitted = 0
        for batch_index, task_id in enumerate(task_ids):
            task = db.get(Task, task_id)
            if not task_is_writable(task):
                continue
            studio_print(
                "image",
                f"ComfyUI 后台提交 batch={batch_index + 1}/{batch_count} "
                f"model={model_filename} size={width}x{height}",
            )
            try:
                prompt_id, trace_meta, node_url = await comfyui_image.submit_image_prompt(
                    prompt_for_comfy,
                    model_filename,
                    width,
                    height,
                    reference_image,
                    reference_images,
                    model_key,
                    skip_translate=optimized
                    or not re.search(r"[\u4e00-\u9fff]", prompt_for_comfy or ""),
                    denoise=denoise,
                    negative_prompt=negative_opt or None,
                    use_reactor=use_reactor,
                    db=db,
                    user=user,
                    task_id=task_id,
                )
            except Exception as exc:
                studio_print("image", f"ComfyUI 提交失败: {exc}")
                logger.exception("canvas_image_task async submit failed")
                remaining_ids = task_ids[batch_index:]
                for fail_id in remaining_ids:
                    fail_task = db.get(Task, fail_id)
                    if fail_task and fail_task.status not in (
                        "completed",
                        "failed",
                        "cancelled",
                    ):
                        _mark_task_terminal(
                            fail_task, status="failed", error=f"提交失败: {exc}"
                        )
                # 未成功进队列的任务退还配额
                if remaining_ids:
                    refund_quota(db, user_id, "image", len(remaining_ids))
                db.commit()
                tasks_cache.invalidate_tasks_cache()
                return

            if batch_index == 0:
                await push_trace(
                    4,
                    "WORKFLOW",
                    {
                        "trace_id": trace_id,
                        **trace_meta["workflow"],
                        "reference_count": trace_meta["workflow"].get(
                            "reference_count", 0
                        ),
                        "workflow_mode": trace_meta["workflow"].get(
                            "workflow_mode", "txt2img"
                        ),
                    },
                )

            task = reload_task_if_active(db, db.get(Task, task_id))
            if task:
                _assign_comfy_submission(
                    task,
                    comfy_prompt_id=prompt_id,
                    node_url=node_url,
                )
                task.status = "pending"
                task.error = None
                task.prompt_text = prompt
                db.commit()
                submitted += 1
                studio_print(
                    "image",
                    f"后台入库完成 task_id={task_id} comfy_prompt_id={prompt_id}",
                )

        tasks_cache.invalidate_tasks_cache()
        studio_print("image", f"后台提交完成 submitted={submitted}/{batch_count}")
    except Exception as e:
        logger.exception("canvas_image async failed")
        unsubmitted = 0
        for tid in task_ids:
            task = db.get(Task, tid)
            if task and task.status not in ("completed", "failed", "cancelled"):
                if not task.comfyui_prompt_id:
                    unsubmitted += 1
                _mark_task_terminal(task, status="failed", error=f"提交失败: {e}")
        if unsubmitted:
            refund_quota(db, user_id, "image", unsubmitted)
        db.commit()
        tasks_cache.invalidate_tasks_cache()
    finally:
        db.close()


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

        trace_id = (body.trace_id or "").strip() or str(uuid.uuid4())
        preset_id = normalize_quality_preset_id(body.quality_preset_id)

        display_for_trace = (body.display_prompt or "").strip() or None
        await push_trace(
            1,
            "SUBMIT",
            {
                "trace_id": trace_id,
                "task_type": "image",
                "model": body.model.strip(),
                "prompt": raw_prompt,
                "display_prompt": display_for_trace,
                "quality_preset_id": preset_id if preset_id != "auto" else None,
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
        mention_ctx = resolve_mentions(
            db,
            user,
            body.mentions,
            project_id=getattr(body, "project_id", None),
            team_id=body.team_id,
        )
        prompt = enrich_prompt(clean_prompt, mention_ctx.get("context_parts") or [])
        pos_suffix, neg_suffix_preset = get_suffixes(preset_id)
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

        project_id = (getattr(body, "project_id", None) or "").strip() or None
        model_key = body.model.strip()
        if project_id:
            from services.canvas_access import get_accessible_project
            from services.generation_memory_service import (
                apply_image_defaults_from_memory,
                get_project_generation_memory,
            )

            project = get_accessible_project(db, user, project_id)
            memory = get_project_generation_memory(project)
            reference_image, reference_images, model_override = apply_image_defaults_from_memory(
                memory,
                model_id=model_key,
                reference_image=reference_image,
                reference_images=reference_images,
            )
            if model_override:
                model_key = model_override

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

        # model_key may have been overridden by project generation memory
        if not model_key:
            model_key = body.model.strip()
        quality_for_dim = body.quality
        width, height = resolve_canvas_image_dimensions(
            model_key,
            body.ratio,
            quality_for_dim,
            width=body.width,
            height=body.height,
        )

        row = db.get(RegisteredModel, model_key)
        if not row:
            raise HTTPException(status_code=400, detail=f"模型不存在: {model_key}")
        if not row.enabled:
            raise HTTPException(status_code=400, detail=f"模型未启用: {model_key}")
        if row.category != "image":
            raise HTTPException(status_code=400, detail=f"模型类别不是图像: {model_key}")
        model_filename = (row.comfyui_file or "").strip()
        if not model_filename:
            raise HTTPException(
                status_code=400,
                detail=f"模型未配置 ComfyUI 权重文件: {body.model}",
            )

        profile = resolve_generation_profile(model_key, model_filename)
        has_ref = bool(reference_images) or bool(reference_image)
        wf = profile.get("workflow_type")
        img2img = profile.get("img2img_support")
        if has_ref and img2img == "unsupported" and wf not in comfyui_image._QWEN_REF_WORKFLOW_TYPES:
            raise HTTPException(
                status_code=400,
                detail=f"模型 {model_key} 不支持参考图/img2img，请移除参考图或更换支持图生图的模型",
            )
        if wf == "flux_pulid" and not has_ref:
            raise HTTPException(status_code=400, detail="flux-pulid 需要角色正脸参考图")
        if wf == "qwen-image-edit" and not has_ref:
            raise HTTPException(status_code=400, detail="qwen-image-edit 需要参考图")
        if wf == "qwen-image-restore" and not has_ref:
            raise HTTPException(status_code=400, detail="qwen-image-restore 需要参考图")
        if wf == "qwen-image-material" and len(reference_images) < 2:
            raise HTTPException(
                status_code=400,
                detail="qwen-image-material 需要主图与材质参考图",
            )

        batch_count = max(1, min(int(body.count or 1), 4))

        await _release_stale_node_tasks_async(db, body.node_id, user.id)
        await reconcile_active_tasks_from_comfyui(db, user.id)
        await check_concurrent_generations(db, user, slots_needed=batch_count, team_id=body.team_id)
        consumed = 0
        try:
            for _ in range(batch_count):
                check_and_consume(db, user.id, "image")
                consumed += 1
        except QuotaExceededError as e:
            if consumed:
                refund_quota(db, user.id, "image", consumed)
            _release_acquired_slots(user.id, team_id=body.team_id, slots=batch_count)
            raise HTTPException(status_code=429, detail=e.message) from e

        await push_trace(
            2,
            "RECEIVED",
            {
                "trace_id": trace_id,
                "model": body.model.strip(),
                "prompt": prompt,
                "quality_preset_id": preset_id if preset_id != "auto" else None,
                "ratio": body.ratio,
                "count": batch_count,
            },
        )
        studio_print(
            "trace",
            f"L2 RECEIVED trace_id={trace_id} model={body.model} prompt_len={len(prompt)} count={batch_count}",
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

        negative_in = (body.negative_prompt or "").strip()
        if neg_suffix_preset and not negative_in:
            negative_in = neg_suffix_preset

        if settings.agent_mock_generation:
            # MOCK PROVIDER — 移除时机：ComfyUI 真实模型接入后
            image_gen_params = build_image_generation_params(
                ratio=body.ratio,
                quality=body.quality,
                width=width,
                height=height,
                reference_images=reference_images,
                use_reactor=bool(getattr(body, "use_reactor", False)),
                mock=True,
                project_id=project_id,
                identity_ids=getattr(body, "identity_ids", None),
                entity_ref_audit=getattr(body, "entity_ref_audit", None),
            )
            prompt_before_optimize = prompt
            positive, negative_opt, optimized = await _translate_for_generation(
                prompt, negative_in, "image", True, model_hint=model_key
            )
            positive = _finalize_image_positive_for_model(
                positive,
                model_key=model_key,
                model_filename=model_filename,
                quality_preset_id=preset_id,
            )
            l3_trace = {
                "trace_id": trace_id,
                "before": prompt_before_optimize,
                "after": positive,
                "optimized": optimized,
                "negative_before": negative_in or None,
                "negative_after": negative_opt or None,
            }
            await push_trace(3, "TRANSLATED", l3_trace)
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
                    original_input=raw_prompt,
                    compiled_prompt=positive,
                    model_id=model_key,
                    generation_params=image_gen_params,
                )
                task_ids.append(task_id)
            db.commit()
            await push_trace(
                4,
                "WORKFLOW",
                build_mock_workflow_trace(
                    "image",
                    trace_id=trace_id,
                    positive_prompt=positive,
                    reference_count=len(reference_images),
                    width=width,
                    height=height,
                    denoise=body.denoise,
                    model_file=model_filename,
                ),
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

        image_gen_params = build_image_generation_params(
            ratio=body.ratio,
            quality=body.quality,
            width=width,
            height=height,
            reference_images=reference_images,
            use_reactor=bool(getattr(body, "use_reactor", False)),
            mock=False,
            project_id=project_id,
            identity_ids=getattr(body, "identity_ids", None),
            entity_ref_audit=getattr(body, "entity_ref_audit", None),
        )
        task_ids = []
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
                comfyui_prompt_id=None,
                node_id=body.node_id,
                original_input=raw_prompt,
                model_id=model_key,
                generation_params=image_gen_params,
            )
            task_ids.append(task_id)
        db.commit()
        if project_id:
            from services.canvas_access import get_accessible_project
            from services.generation_memory_service import record_shot_generation

            project = get_accessible_project(db, user, project_id)
            face_url = reference_image if model_key == "flux-pulid" else None
            record_shot_generation(
                project,
                model_id=model_key,
                ratio=body.ratio,
                quality=body.quality,
                protagonist_face_url=face_url,
            )
            db.commit()
        tasks_cache.invalidate_tasks_cache()
        asyncio.create_task(
            _run_canvas_image_submit_task(
                task_ids,
                user_id=user.id,
                team_id=body.team_id,
                prompt=prompt,
                negative_in=negative_in,
                reference_image=reference_image,
                reference_images=reference_images,
                model_key=model_key,
                model_filename=model_filename,
                width=width,
                height=height,
                denoise=body.denoise,
                use_reactor=bool(getattr(body, "use_reactor", False)),
                ratio=body.ratio,
                quality=body.quality,
                trace_id=trace_id,
                quality_preset_id=preset_id,
            )
        )
        studio_print("image", f"已入库异步提交 task_ids={task_ids}")
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
        from services.media_access import resolve_image_reference_path

        path = resolve_image_reference_path(db, user, image_url)
        data = path.read_bytes()
    return base64.b64encode(data).decode("ascii")


async def _audio_url_to_comfy_filename(
    audio_url: str,
    *,
    db: Session,
    user: User,
    node_url: str | None = None,
) -> str:
    """将画布音频 URL 上传到 ComfyUI input，返回 VHS_LoadAudioUpload 可用的 filename。"""
    from services.media_access import (
        assert_user_can_read_upload_url,
        normalize_media_reference_url,
    )

    raw = normalize_media_reference_url((audio_url or "").strip())
    if not raw:
        raise ValueError("音频地址不能为空")

    data: bytes
    fname = "input.mp3"
    mime = "audio/mpeg"

    if raw.startswith("http://") or raw.startswith("https://"):
        async with httpx.AsyncClient(timeout=60.0) as client:
            res = await client.get(raw)
            res.raise_for_status()
            data = res.content
            fname = raw.split("/")[-1].split("?", 1)[0] or "input.mp3"
    else:
        path = assert_user_can_read_upload_url(db, user, raw)
        data = path.read_bytes()
        fname = path.name or "input.mp3"

    suffix = Path(fname).suffix.lower()
    mime_map = {
        ".mp3": "audio/mpeg",
        ".wav": "audio/wav",
        ".m4a": "audio/mp4",
        ".ogg": "audio/ogg",
        ".flac": "audio/flac",
    }
    mime = mime_map.get(suffix, mime)

    async with httpx.AsyncClient(timeout=60.0) as client:
        res = await client.post(
            f"{comfyui._resolve_comfyui_base(node_url)}/upload/image",
            files={"image": (fname, data, mime)},
        )
        res.raise_for_status()
        name = res.json().get("name")
    if not name:
        raise ValueError("音频上传 ComfyUI 失败")
    return name


async def _run_canvas_video_submit_task(
    task_id: str,
    *,
    user_id: int,
    team_id: str | None,
    batch_count: int,
    prompt: str,
    neg_suffix: str,
    pos_suffix: str,
    mode: str,
    first_frame: str | None,
    last_frame: str | None,
    ref_image: str | None,
    model_id: str,
    model_entry: dict | None,
    video_backend: str,
    aligned_w: int,
    aligned_h: int,
    duration: int,
    ratio: str,
    resolution: str,
    audio: bool,
    client_id: str | None,
    sampling_profile: str | None,
    steps: int | None,
    use_distilled: bool,
    cfg_distilled: bool,
    use_cache: bool | None,
    camera_move: str | None,
    shot_scale: str | None,
    sound_note: str | None,
    use_reactor: bool,
    reactor_face: str | None,
    trace_id: str,
    audio_url: str | None = None,
) -> None:
    """后台：参考图转码 + optimize + Comfy/Seedance 提交。"""
    from db.session import SessionLocal

    db = SessionLocal()
    try:
        task = db.get(Task, task_id)
        if not task_is_writable(task):
            return
        task.status = "processing"
        task.error = None
        db.commit()

        user = db.get(User, user_id)
        if not user:
            raise ValueError("用户不存在")

        image_b64 = None
        start_image_b64 = None
        end_image_b64 = None
        if mode == "fun_inpaint":
            start_image_b64 = await _image_url_to_base64(first_frame, db=db, user=user)
            end_image_b64 = await _image_url_to_base64(last_frame, db=db, user=user)
        elif mode == "flf2v":
            start_image_b64 = await _image_url_to_base64(first_frame, db=db, user=user)
            end_image_b64 = await _image_url_to_base64(last_frame, db=db, user=user)
        elif mode == "image2video" and ref_image:
            image_b64 = await _image_url_to_base64(ref_image, db=db, user=user)

        # Wan：运镜/景别注入到 prompt（与 /api/prompt/compile 一致）
        if video_backend == "wan" and (
            (camera_move or "auto") != "auto" or (shot_scale or "auto") != "auto"
        ):
            try:
                from services.prompt_builder import build_prompt

                compiled = build_prompt(
                    prompt,
                    model_target="wan-t2v" if mode == "text2video" else "wan-i2v",
                    camera_move=camera_move or "auto",
                    shot_scale=shot_scale or "auto",
                )
                prompt = compiled.positive_prompt or prompt
            except Exception:
                logger.exception("wan camera/shot inject failed; continue without")

        prompt_before_optimize = prompt
        if video_backend == "ltx2":
            video_model_hint = model_id or "ltx2-fp4"
        else:
            video_model_hint = model_id
        try:
            positive, negative, optimized, _ = await maybe_optimize_prompt(
                prompt, neg_suffix, "video", True, model_hint=video_model_hint
            )
        except PromptTranslationError as exc:
            raise ValueError(str(exc)) from exc
        if video_backend == "ltx2":
            positive = build_ltx2_prompt(positive)
            negative = merge_ltx2_negative(negative)
        elif video_backend == "ltx23":
            positive = build_ltx23_prompt(positive)
            negative = merge_ltx23_negative(negative)
        elif video_backend == "wan":
            positive = build_wan_prompt(positive)
            negative = merge_wan_negative(negative)
        else:
            positive = apply_video_anatomy_guard(positive)
        translated_positive = positive
        if pos_suffix:
            positive = f"{positive}, {pos_suffix}" if positive.strip() else pos_suffix
        l3_trace = {
            "trace_id": trace_id,
            "before": prompt_before_optimize,
            "after": translated_positive,
            "after_final": positive,
            "optimized": optimized,
        }
        await push_trace(3, "TRANSLATED", l3_trace)

        # 注意：后续 reload_task_if_active 会 expire，compiled_prompt 须在 commit 前再写一次
        compiled_prompt_final = positive

        model_ckpt = (model_entry or {}).get("comfyui_model_file")
        if video_backend == "ltx":
            model_ckpt = comfyui.LTX_CKPT or model_ckpt
        elif video_backend == "ltx2":
            model_ckpt = (model_entry or {}).get("comfyui_model_file") or comfyui.LTX2_CKPT
        elif video_backend == "ltx23":
            model_ckpt = (model_entry or {}).get("comfyui_model_file") or comfyui.LTX23_UNET

        if video_backend == "seedance":
            from providers.seedance import SeedanceClient
            from services.prompt_builder import compress_for_seedance
            from services.seedance_task_service import run_seedance_video_task

            client = SeedanceClient()
            if not client.is_configured():
                raise ValueError("未配置 SEEDANCE_API_KEY，无法提交 Seedance 任务")
            compressed = compress_for_seedance(
                positive,
                camera_move=camera_move or "auto",
                shot_scale=shot_scale or "auto",
            )
            task = reload_task_if_active(db, db.get(Task, task_id))
            if not task:
                return
            task.comfyui_prompt_id = "seedance:pending"
            task.prompt_text = compressed.positive_prompt
            task.compiled_prompt = compressed.positive_prompt
            task.status = "pending"
            task.error = None
            db.commit()
            await push_trace(
                4,
                "WORKFLOW",
                build_mock_workflow_trace(
                    "video",
                    trace_id=trace_id,
                    positive_prompt=compressed.positive_prompt,
                    width=aligned_w,
                    height=aligned_h,
                    workflow_mode="seedance",
                    duration=duration,
                ),
            )
            asyncio.create_task(
                run_seedance_video_task(
                    task_id,
                    prompt=compressed.positive_prompt,
                    ratio=ratio,
                    duration=int(duration),
                    resolution=str(resolution or "720p"),
                )
            )
            tasks_cache.invalidate_tasks_cache()
            studio_print("video", f"后台 seedance 提交 task_id={task_id}")
            return

        video_submit_kwargs = dict(
            prompt=positive,
            negative_prompt=negative,
            duration=duration,
            width=aligned_w,
            height=aligned_h,
            mode=mode,
            image_b64=image_b64,
            start_image_b64=start_image_b64,
            end_image_b64=end_image_b64,
            raw_prompt=optimized,
            client_id=client_id,
            model_filename=model_ckpt,
        )
        if video_backend == "ltx2":
            video_submit_kwargs["audio"] = bool(audio)
            # LTX2 默认走 quality 档；前端 sampling_profile 此前对 LTX2 无效
            video_submit_kwargs["sampling_profile"] = (
                sampling_profile or "quality"
            ).strip().lower() or "quality"
            # 纯文生超过 10 秒稳定性差（反馈集中），硬顶 10s
            if mode == "text2video" and int(duration) > 10:
                logger.info(
                    "ltx2 t2v duration clamp %ss→10s task_id=%s",
                    duration,
                    task_id,
                )
                video_submit_kwargs["duration"] = 10
                duration = 10

        comfy_node_url: str | None = None
        if video_backend == "wan":
            comfy_prompt_id, _client_id, workflow, comfy_node_url = (
                await comfyui.submit_wan_video_prompt(
                **video_submit_kwargs,
                sampling_profile=sampling_profile or "quality",
                )
            )
            trace_ckpt = model_ckpt or comfyui.WAN_CKPT
        elif video_backend == "ltx2":
            comfy_prompt_id, _client_id, workflow, comfy_node_url = (
                await comfyui.submit_ltx2_video_prompt(
                **video_submit_kwargs
                )
            )
            trace_ckpt = model_ckpt or comfyui.LTX2_CKPT
        elif video_backend == "ltx23":
            if mode != "image2video":
                raise ValueError("ltx23-i2av 仅支持图生视频")
            if not image_b64:
                raise ValueError("图生视频需要上传图片")
            reserved_node = comfyui._acquire_gpu_node_url(
                estimated_duration_sec=max(120, duration * 30),
                required_vram=24,
            )
            image_filename = await comfyui.upload_image_base64(
                image_b64, node_url=reserved_node
            )
            audio_filename = None
            if audio_url:
                audio_filename = await _audio_url_to_comfy_filename(
                    audio_url,
                    db=db,
                    user=user,
                    node_url=reserved_node,
                )
            await comfyui.ensure_video_mp4_capable(reserved_node)
            workflow = comfyui.build_ltx23_i2av_workflow(
                positive,
                negative,
                image_filename,
                audio_filename=audio_filename,
                width=aligned_w,
                height=aligned_h,
                duration_sec=duration,
                sampling_profile=(sampling_profile or "quality").strip().lower()
                or "quality",
            )
            comfy_prompt_id, _client_id, workflow, comfy_node_url = (
                await comfyui._log_and_post_video_workflow(
                    workflow,
                    client_id=client_id,
                    backend="ltx23",
                    width=aligned_w,
                    height=aligned_h,
                    duration=duration,
                    mode=mode,
                    node_url=reserved_node,
                )
            )
            trace_ckpt = model_ckpt or comfyui.LTX23_UNET
        else:
            comfy_prompt_id, _client_id, workflow, comfy_node_url = (
                await comfyui.submit_video_prompt(
                **video_submit_kwargs
                )
            )
            trace_ckpt = comfyui.LTX_CKPT

        workflow_trace = extract_workflow_trace(workflow, trace_ckpt)
        workflow_trace["trace_id"] = trace_id
        workflow_trace["task_type"] = "video"
        workflow_trace["duration"] = duration
        await push_trace(4, "WORKFLOW", workflow_trace)

        task = reload_task_if_active(db, db.get(Task, task_id))
        if not task:
            stale = db.get(Task, task_id)
            studio_print(
                "video",
                f"跳过后台提交 task_id={task_id} 任务已终态 status={getattr(stale, 'status', None)}",
            )
            return
        _assign_comfy_submission(
            task,
            comfy_prompt_id=comfy_prompt_id,
            node_url=comfy_node_url,
        )
        task.compiled_prompt = compiled_prompt_final
        task.status = "pending"
        task.error = None
        db.commit()
        tasks_cache.invalidate_tasks_cache()
        studio_print(
            "video",
            f"后台提交完成 task_id={task_id} comfy_prompt_id={comfy_prompt_id}",
        )
    except Exception as e:
        err = str(e)
        if isinstance(e, httpx.ConnectError):
            err = "ComfyUI 服务未启动，请先启动 ComfyUI（端口 8000）"
        elif isinstance(e, httpx.HTTPStatusError):
            err = f"ComfyUI 返回错误: {e.response.status_code}"
        task = db.get(Task, task_id)
        if task and task.status != "cancelled":
            _mark_task_terminal(task, status="failed", error=err[:2000])
            if not comfy_id_counts_as_executed(task):
                refund_quota(db, user_id, "video", 1)
            db.commit()
            tasks_cache.invalidate_tasks_cache()
        elif not task:
            _release_acquired_slots(user_id, team_id=team_id, slots=batch_count)
        logger.exception("canvas_video async submit failed task_id=%s", task_id)
    finally:
        db.close()


# ── Canvas: video generation ──────────────────────────────────────────────────

@router.post("/api/tasks/video")
async def canvas_video_task(
    body: CanvasVideoRequestExt,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """画布视频生成卡片接口。
    将 ratio + resolution 通过 RESOLUTION_MAP 转为像素宽高；
    duration 和 audio 透传给模型调用函数；
    按 model 分派到 call_wan / call_ltx。
    返回 task_id 供前端轮询/WebSocket 回填结果。
    """
    raw_prompt = body.prompt.strip()
    if not raw_prompt:
        raise HTTPException(status_code=400, detail="请填写画面描述")

    trace_id = (body.trace_id or "").strip() or str(uuid.uuid4())
    preset_id = normalize_quality_preset_id(body.quality_preset_id)

    if (
        body.generation_mode == "keyframe"
        and body.last_frame
        and not body.first_frame
    ):
        raise HTTPException(status_code=400, detail="首尾帧模式需要首帧图片")

    await push_trace(
        1,
        "SUBMIT",
        {
            "trace_id": trace_id,
            "task_type": "video",
            "model": body.model.strip(),
            "prompt": raw_prompt,
            "quality_preset_id": preset_id if preset_id != "auto" else None,
            "ratio": body.ratio,
            "resolution": body.resolution,
            "count": body.count,
            "generation_mode": body.generation_mode,
            "first_frame": body.first_frame,
            "last_frame": body.last_frame,
        },
    )
    studio_print(
        "trace",
        f"L1 SUBMIT model={body.model} ratio={body.ratio} "
        f"resolution={body.resolution} count={body.count} "
        f"generation_mode={body.generation_mode} "
        f"first_frame={'yes' if body.first_frame else 'no'} "
        f"last_frame={'yes' if body.last_frame else 'no'}",
    )

    clean_prompt = strip_mention_tokens(raw_prompt)
    mention_ctx = resolve_mentions(
        db,
        user,
        body.mentions,
        project_id=getattr(body, "project_id", None),
        team_id=body.team_id,
    )
    prompt = enrich_prompt(clean_prompt, mention_ctx.get("context_parts") or [])

    pos_suffix, neg_suffix = get_suffixes(preset_id)

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

    model_id = body.model.strip()
    model_entry = MODEL_MAP.get(model_id) or MODEL_MAP.get(model_id.lower())
    model_caps = (model_entry or {}).get("capabilities") or {}
    if model_id == "ltx23-i2av":
        if body.duration < 3 or body.duration > 30:
            raise HTTPException(
                status_code=400,
                detail=f"{model_id} 视频时长支持 3–30 秒",
            )
    else:
        allowed_durations = model_caps.get("durations")
        if not isinstance(allowed_durations, list) or not allowed_durations:
            allowed_durations = [5, 10, 15]
        allowed_durations = [int(d) for d in allowed_durations]
        if body.duration not in allowed_durations:
            opts = " / ".join(str(d) for d in allowed_durations)
            raise HTTPException(
                status_code=400,
                detail=f"视频时长仅支持 {opts} 秒",
            )

    allowed_ratios = model_caps.get("aspect_ratios") or []
    if allowed_ratios and body.ratio not in allowed_ratios:
        opts = " / ".join(str(r) for r in allowed_ratios)
        raise HTTPException(
            status_code=400,
            detail=f"该模型不支持宽高比 {body.ratio}，可选：{opts}",
        )

    allowed_res = get_video_allowed_resolutions(body.model.strip())
    res_norm = str(body.resolution or "").strip().upper()
    if allowed_res and res_norm not in allowed_res:
        opts = " / ".join(allowed_res)
        raise HTTPException(
            status_code=400,
            detail=f"该模型不支持清晰度 {body.resolution}，可选：{opts}",
        )
    # 规范化后用于 RESOLUTION_MAP 查找
    body_resolution = res_norm or body.resolution

    if body.audio and not bool(model_caps.get("supports_audio")):
        body.audio = False

    # 解析分辨率（探针可同时传 width+height 覆盖）
    override_w = getattr(body, "width", None)
    override_h = getattr(body, "height", None)
    if override_w is not None and override_h is not None:
        width, height = int(override_w), int(override_h)
    else:
        res_key = (body.ratio, body_resolution)
        if res_key not in RESOLUTION_MAP:
            raise HTTPException(
                status_code=400,
                detail=f"不支持的比例/清晰度组合: {body.ratio} · {body_resolution}",
            )
        width, height = RESOLUTION_MAP[res_key]
    video_backend = resolve_video_backend(body.model.strip())
    # LTX2 / Wan：480P 观感差，自动升到 720P（显式 width/height 覆盖除外）
    if (
        video_backend in ("ltx2", "ltx23", "wan")
        and override_w is None
        and override_h is None
        and str(body_resolution).upper() == "480P"
    ):
        body_resolution = "720P"
        res_key = (body.ratio, body_resolution)
        if res_key in RESOLUTION_MAP:
            width, height = RESOLUTION_MAP[res_key]
            logger.info(
                "%s auto-upgrade resolution 480P→720P ratio=%s",
                video_backend,
                body.ratio,
            )
    if video_backend in ("ltx", "ltx2", "ltx23"):
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

    batch_count = 1
    await _release_stale_node_tasks_async(db, body.node_id, user.id)
    await reconcile_active_tasks_from_comfyui(db, user.id)

    model_id = (body.model or "").strip()
    _early_ref = first_frame or reference_image or (reference_images[0] if reference_images else None)
    _early_mode = "text2video"
    if model_id == "wan-fun-inpaint" and first_frame and last_frame:
        _early_mode = "fun_inpaint"
    elif body.generation_mode == "keyframe" and first_frame and last_frame and first_frame != last_frame:
        _early_mode = "flf2v"
    elif _early_ref:
        _early_mode = "image2video"
    if _is_deprecated_hunyuan_model(model_id):
        replacement = remap_deprecated_video_model(model_id, mode=_early_mode)
        logger.info(
            "deprecated video model %s → %s (mode=%s)",
            model_id,
            replacement,
            _early_mode,
        )
        model_id = replacement
        video_backend = resolve_video_backend(model_id)
    row = db.get(RegisteredModel, model_id)
    if not row:
        raise HTTPException(status_code=400, detail=f"模型不存在: {body.model}")
    if not row.enabled:
        raise HTTPException(status_code=400, detail=f"模型未启用: {body.model}")
    if row.category != "video":
        raise HTTPException(status_code=400, detail=f"模型类别不是视频: {body.model}")

    await check_concurrent_generations(db, user, slots_needed=batch_count, team_id=body.team_id)
    ref_image = first_frame or reference_image
    if not ref_image and reference_images:
        ref_image = reference_images[0]
    if model_id == "ltx23-i2av" and not ref_image:
        raise HTTPException(
            status_code=400,
            detail=f"{model_id} 需要参考图",
        )

    use_fun_inpaint = model_id == "wan-fun-inpaint"
    # 首尾同图视为单帧 I2V，不能走 FLF2V
    use_flf2v = (
        not use_fun_inpaint
        and body.generation_mode == "keyframe"
        and bool(first_frame)
        and bool(last_frame)
        and first_frame != last_frame
    )
    mode = "text2video"
    if use_fun_inpaint:
        if not first_frame or not last_frame:
            raise HTTPException(
                status_code=400,
                detail="wan-fun-inpaint 需要首帧与尾帧（first_frame + last_frame）",
            )
        mode = "fun_inpaint"
    elif use_flf2v:
        mode = "flf2v"
    elif ref_image:
        mode = "image2video"

    # T2V-only 权重不能跑 i2v/flf2v：自动切到 wan-i2v
    t2v_only = {
        "wan-2.6",
        "ltx-video",
    }
    # LTX-2 支持 I2V，但不支持首尾帧 FLF2V → 切 wan-i2v
    if mode == "flf2v" and model_id == "ltx2-fp4":
        model_id = "wan-i2v"
        video_backend = resolve_video_backend(model_id)
    elif mode in ("image2video", "flf2v") and model_id in t2v_only:
        model_id = "wan-i2v"
        video_backend = resolve_video_backend(model_id)

    # Seedance 仅文生：带参考图时强制 text2video（保留 seedance-2.0，不静默改模型）
    if model_id == "seedance-2.0" and mode in ("image2video", "flf2v", "fun_inpaint"):
        mode = "text2video"

    await push_trace(
        2,
        "RECEIVED",
        {
            "trace_id": trace_id,
            "task_type": "video",
            "model": body.model.strip(),
            "prompt": prompt,
            "quality_preset_id": preset_id if preset_id != "auto" else None,
            "ratio": body.ratio,
            "count": batch_count,
            "workflow_route": mode,
            "generation_mode": body.generation_mode,
        },
    )
    studio_print(
        "trace",
        f"L2 RECEIVED trace_id={trace_id} model={body.model} prompt_len={len(prompt)} "
        f"count={batch_count} workflow_route={mode}",
    )
    try:
        check_and_consume(db, user.id, "video")
    except QuotaExceededError as e:
        _release_acquired_slots(user.id, team_id=body.team_id, slots=batch_count)
        raise HTTPException(status_code=429, detail=e.message) from e

    sound_note = (body.sound_note or "").strip() or None
    reactor_face = (body.reactor_face_image or "").strip() or None
    use_reactor = bool(body.use_reactor) and bool(reactor_face)

    sampling_profile, sampling_upgrade_reason = resolve_video_sampling_profile(
        sampling_profile=getattr(body, "sampling_profile", None),
        generation_mode=body.generation_mode,
        workflow_mode=mode,
        has_reference_image=bool(ref_image),
        prompt=prompt,
        video_backend=video_backend,
    )
    if sampling_upgrade_reason:
        logger.info(
            "video sampling_profile fast→quality: reason=%s node_id=%s task_mode=%s",
            sampling_upgrade_reason,
            body.node_id,
            mode,
        )
        studio_print(
            "video",
            f"高风险 freeref I2V 自动升档 quality ({sampling_upgrade_reason})",
        )

    video_gen_params = build_video_generation_params(
        ratio=body.ratio,
        resolution=body.resolution,
        duration=body.duration,
        mode=mode,
        width=aligned_w,
        height=aligned_h,
        reference_images=reference_images,
        use_reactor=use_reactor,
        mock=settings.agent_mock_generation,
        project_id=(getattr(body, "project_id", None) or "").strip() or None,
        identity_ids=getattr(body, "identity_ids", None),
        entity_ref_audit=getattr(body, "entity_ref_audit", None),
    )

    if settings.agent_mock_generation:
        prompt_before_optimize = prompt
        if video_backend == "ltx2":
            video_model_hint = model_id or "ltx2-fp4"
        else:
            video_model_hint = model_id
        positive, negative, optimized = await _translate_for_generation(
            prompt, neg_suffix, "video", True, model_hint=video_model_hint
        )
        if video_backend == "ltx2":
            positive = build_ltx2_prompt(positive)
            negative = merge_ltx2_negative(negative)
        elif video_backend == "ltx23":
            positive = build_ltx23_prompt(positive)
            negative = merge_ltx23_negative(negative)
        elif video_backend == "wan":
            positive = build_wan_prompt(positive)
            negative = merge_wan_negative(negative)
        else:
            positive = apply_video_anatomy_guard(positive)
        translated_positive = positive
        if pos_suffix:
            positive = f"{positive}, {pos_suffix}" if positive.strip() else pos_suffix
        l3_trace = {
            "trace_id": trace_id,
            "before": prompt_before_optimize,
            "after": translated_positive,
            "after_final": positive,
            "optimized": optimized,
        }
        await push_trace(3, "TRANSLATED", l3_trace)
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
            sound_note=sound_note,
            video_backend=video_backend,
            use_reactor=use_reactor,
            reactor_face_image=reactor_face if use_reactor else None,
            original_input=raw_prompt,
            compiled_prompt=positive,
            model_id=model_id,
            generation_params=video_gen_params,
        )
        db.commit()
        tasks_cache.invalidate_tasks_cache()
        await push_trace(
            4,
            "WORKFLOW",
            build_mock_workflow_trace(
                "video",
                trace_id=trace_id,
                positive_prompt=positive,
                width=aligned_w,
                height=aligned_h,
                workflow_mode=mode,
                duration=body.duration,
            ),
        )
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

    task_id = str(uuid.uuid4())
    create_task_record(
        db,
        task_id,
        "video",
        "pending",
        user_id=user.id,
        team_id=body.team_id,
        prompt_text=prompt,
        comfyui_prompt_id=None,
        node_id=body.node_id,
        sound_note=sound_note,
        video_backend=video_backend,
        use_reactor=use_reactor,
        reactor_face_image=reactor_face if use_reactor else None,
        original_input=raw_prompt,
        model_id=model_id,
        generation_params=video_gen_params,
    )
    db.commit()
    video_project_id = (getattr(body, "project_id", None) or "").strip() or None
    if video_project_id:
        from services.canvas_access import get_accessible_project
        from services.generation_memory_service import record_shot_generation

        project = get_accessible_project(db, user, video_project_id)
        record_shot_generation(
            project,
            model_id=model_id,
            ratio=body.ratio,
            quality=body.resolution,
        )
        db.commit()
    tasks_cache.invalidate_tasks_cache()
    asyncio.create_task(
        _run_canvas_video_submit_task(
            task_id,
            user_id=user.id,
            team_id=body.team_id,
            batch_count=batch_count,
            prompt=prompt,
            neg_suffix=neg_suffix or "",
            pos_suffix=pos_suffix or "",
            mode=mode,
            first_frame=first_frame,
            last_frame=last_frame,
            ref_image=ref_image,
            model_id=model_id,
            model_entry=model_entry,
            video_backend=video_backend,
            aligned_w=aligned_w,
            aligned_h=aligned_h,
            duration=body.duration,
            ratio=body.ratio,
            resolution=body_resolution,
            audio=bool(body.audio),
            client_id=body.client_id,
            sampling_profile=sampling_profile,
            steps=getattr(body, "steps", None),
            use_distilled=bool(getattr(body, "use_distilled", False)),
            cfg_distilled=bool(getattr(body, "cfg_distilled", False)),
            use_cache=getattr(body, "use_cache", None),
            camera_move=getattr(body, "camera_move", None),
            shot_scale=getattr(body, "shot_scale", None),
            sound_note=sound_note,
            use_reactor=use_reactor,
            reactor_face=reactor_face if use_reactor else None,
            trace_id=trace_id,
            audio_url=(body.audio_url or "").strip() or None,
        )
    )
    studio_print("video", f"已入库异步提交 task_id={task_id} backend={video_backend}")
    return {
        "task_id": task_id,
        "comfy_prompt_id": None,
        "status": "pending",
    }


# ── Canvas: video enhance ─────────────────────────────────────────────────────

TASK_TYPE_VE_RECO = "ve_reco"


@router.get("/api/tasks/video-enhance/config")
async def video_enhance_config(_: User = Depends(get_current_user)):
    """前端画质增强面板：可用规模与默认选型（5090 仅 3B 时自动降级）。"""
    from model_registry import resolve_video_enhance_workflow
    from services.registered_model_sync import default_seedvr_model_size, seedvr_available_model_sizes

    sizes = seedvr_available_model_sizes()
    resolved = None if settings.agent_mock_generation else resolve_video_enhance_workflow("auto")
    available = bool(sizes) and (settings.agent_mock_generation or resolved is not None)
    return {
        "available": available,
        "available_model_sizes": sizes,
        "default_model_size": default_seedvr_model_size() if sizes else None,
    }


async def _run_video_enhance_recommend_task(
    task_id: str,
    *,
    user_id: int,
    video_url: str,
    project_id: str | None,
    script_table_node_id: str | None,
) -> None:
    from db.session import SessionLocal
    from services.media_access import resolve_video_source_for_enhance
    from services.video_enhance_probe import probe_video_info_from_url
    from services.video_enhance_recommend import recommend_enhance_params

    db = SessionLocal()
    try:
        task = db.get(Task, task_id)
        if not task_is_writable(task):
            return
        task.status = "processing"
        task.error = None
        db.commit()

        user = db.get(User, user_id)
        if not user:
            raise ValueError("用户不存在")

        try:
            resolve_video_source_for_enhance(db, user, video_url)
        except HTTPException as e:
            raise ValueError(e.detail if isinstance(e.detail, str) else "视频源无效或无权访问") from e

        try:
            video_info = await probe_video_info_from_url(db, user, video_url)
        except HTTPException as e:
            raise ValueError(e.detail if isinstance(e.detail, str) else "无法分析视频属性") from e
        except Exception as e:
            raise ValueError("无法分析视频属性") from e

        quality_preset_id = "auto"
        if project_id:
            from services.canvas_access import get_accessible_project
            from services.canvas_style_ref import (
                get_script_table_default_quality_preset,
                load_canvas_data,
            )

            project = get_accessible_project(db, user, project_id)
            if project:
                canvas_data = load_canvas_data(project)
                quality_preset_id = get_script_table_default_quality_preset(
                    canvas_data, script_table_node_id
                )

        use_llm = not settings.agent_mock_generation
        params, reasoning = await recommend_enhance_params(
            video_info,
            use_llm=use_llm,
            quality_preset_id=quality_preset_id,
        )
        task = db.get(Task, task_id)
        if task_is_writable(task):
            task.status = "completed"
            task.error = None
            task.result = json.dumps(
                {"params": params, "reasoning": reasoning or ""},
                ensure_ascii=False,
            )
            db.commit()
    except Exception as e:
        task = db.get(Task, task_id)
        if task_is_writable(task):
            task.status = "failed"
            task.error = str(e)[:2000]
            task.result = None
            db.commit()
        logger.exception("video-enhance recommend async failed task_id=%s", task_id)
    finally:
        db.close()


@router.post("/api/tasks/video-enhance/recommend-params")
async def canvas_video_enhance_recommend_params(
    body: VideoEnhanceRecommendRequest,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """分析视频属性并推荐画质增强参数；立即返回 task_id，结果经 GET /api/tasks/{id} 轮询。"""
    video_url = (body.video_url or "").strip()
    if not video_url:
        raise HTTPException(status_code=400, detail="视频地址不能为空")

    from services.media_access import resolve_video_source_for_enhance

    # Fast precheck so obvious bad URLs fail before enqueue
    try:
        resolve_video_source_for_enhance(db, user, video_url)
    except HTTPException as e:
        raise e
    except Exception as e:
        raise HTTPException(status_code=400, detail="视频源无效或无权访问") from e

    task_id = str(uuid.uuid4())
    create_task_record(
        db,
        task_id,
        TASK_TYPE_VE_RECO,
        "queued",
        user_id=user.id,
        prompt_text=video_url[:2000],
    )
    db.commit()
    asyncio.create_task(
        _run_video_enhance_recommend_task(
            task_id,
            user_id=user.id,
            video_url=video_url,
            project_id=body.project_id,
            script_table_node_id=body.script_table_node_id,
        )
    )
    return {"task_id": task_id, "status": "queued"}


async def _run_video_enhance_submit_task(
    task_id: str,
    *,
    user_id: int,
    team_id: str | None,
    video_url: str,
    provider_id: str,
    seedvr2_params: dict,
    client_id: str | None,
    trace_id: str,
) -> None:
    """后台：上传视频到 Comfy 并提交 enhance workflow，写回 comfyui_prompt_id。"""
    from db.session import SessionLocal
    from comfyui.client import map_enhance_submit_error

    db = SessionLocal()
    try:
        task = db.get(Task, task_id)
        if not task_is_writable(task):
            return
        task.status = "processing"
        task.error = None
        db.commit()

        user = db.get(User, user_id)
        if not user:
            raise ValueError("用户不存在")

        upscale_factor = seedvr2_params["upscale_factor"]
        if provider_id == VIDEO_ENHANCE_SEEDVR2_ID:
            comfy_prompt_id, _client_id, workflow, comfy_node_url = (
                await comfyui.submit_seedvr2_enhance_prompt(
                video_url,
                db=db,
                user=user,
                upscale_factor=upscale_factor,
                strength=seedvr2_params["strength"],
                input_noise_scale=seedvr2_params["input_noise_scale"],
                batch_size=seedvr2_params["batch_size"],
                color_correction=seedvr2_params["color_correction"],
                model_size=seedvr2_params["model_size"],
                client_id=client_id,
                )
            )
        else:
            comfy_prompt_id, _client_id, workflow, comfy_node_url = (
                await comfyui.submit_realesrgan_enhance_prompt(
                video_url,
                db=db,
                user=user,
                upscale_factor=upscale_factor,
                client_id=client_id,
                )
            )

        task = db.get(Task, task_id)
        if not task_is_writable(task):
            return

        workflow_trace = extract_enhance_trace(workflow, provider_id)
        workflow_trace["trace_id"] = trace_id
        await push_trace(4, "WORKFLOW", workflow_trace)
        studio_print("trace", f"L4 WORKFLOW video-enhance {workflow_trace}")

        _assign_comfy_submission(
            task,
            comfy_prompt_id=comfy_prompt_id,
            node_url=comfy_node_url,
        )
        task.status = "pending"
        task.error = None
        db.commit()
        tasks_cache.invalidate_tasks_cache()
        studio_print(
            "video-enhance",
            f"后台提交完成 task_id={task_id} provider={provider_id} "
            f"comfy_prompt_id={comfy_prompt_id} node={comfy_node_url}",
        )
    except Exception as e:
        err: str
        if isinstance(e, ValueError):
            err = map_enhance_submit_error(str(e))
        elif isinstance(e, httpx.ConnectError):
            err = "ComfyUI 服务未启动，请先启动 ComfyUI"
        elif isinstance(e, httpx.HTTPStatusError):
            err = f"ComfyUI 返回错误: {e.response.status_code}"
        else:
            err = f"提交失败: {e}"
        task = db.get(Task, task_id)
        if task and task.status != "cancelled":
            _mark_task_terminal(task, status="failed", error=err)
            if not comfy_id_counts_as_executed(task):
                refund_quota(db, user_id, "video", 1)
            db.commit()
            tasks_cache.invalidate_tasks_cache()
        elif not task:
            _release_acquired_slots(user_id, team_id=team_id, slots=1)
        logger.exception("video-enhance submit async failed task_id=%s", task_id)
    finally:
        db.close()


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

    await _release_stale_node_tasks_async(db, body.node_id, user.id)
    await reconcile_active_tasks_from_comfyui(db, user.id)
    await check_concurrent_generations(db, user, slots_needed=1, team_id=body.team_id)

    try:
        check_and_consume(db, user.id, "video")
    except QuotaExceededError as e:
        _release_acquired_slots(user.id, team_id=body.team_id, slots=1)
        raise HTTPException(status_code=429, detail=e.message) from e

    prompt_label = f"video_enhance x{upscale_factor} {body.strength}"
    trace_id = (body.trace_id or "").strip() or str(uuid.uuid4())

    await push_trace(
        1,
        "SUBMIT",
        {
            "trace_id": trace_id,
            "task_type": "video_enhance",
            "video_url": video_url,
            "upscale_factor": upscale_factor,
            "strength": body.strength,
            "batch_size": seedvr2_params["batch_size"],
            "input_noise_scale": seedvr2_params["input_noise_scale"],
            "color_correction": seedvr2_params["color_correction"],
            "workflow": body.workflow,
        },
    )

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
        await push_trace(
            4,
            "WORKFLOW",
            build_mock_workflow_trace(
                "video_enhance",
                trace_id=trace_id,
                provider="mock",
                upscale_factor=upscale_factor,
                strength=body.strength,
                batch_size=seedvr2_params["batch_size"],
                color_correction=seedvr2_params["color_correction"],
            ),
        )
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
    task_id = str(uuid.uuid4())
    create_task_record(
        db,
        task_id,
        "video_enhance",
        "pending",
        user_id=user.id,
        team_id=body.team_id,
        prompt_text=prompt_label,
        comfyui_prompt_id=None,
        node_id=body.node_id,
    )
    db.commit()
    tasks_cache.invalidate_tasks_cache()

    asyncio.create_task(
        _run_video_enhance_submit_task(
            task_id,
            user_id=user.id,
            team_id=body.team_id,
            video_url=video_url,
            provider_id=provider_id,
            seedvr2_params=seedvr2_params,
            client_id=body.client_id,
            trace_id=trace_id,
        )
    )
    studio_print(
        "video-enhance",
        f"已入库异步提交 task_id={task_id} provider={provider_id}",
    )

    return {
        "task_id": task_id,
        "comfy_prompt_id": None,
        "status": "pending",
    }


async def _run_image_enhance_submit_task(
    task_id: str,
    *,
    user_id: int,
    team_id: str | None,
    image_url: str,
    seedvr2_params: dict,
    client_id: str | None,
    trace_id: str,
) -> None:
    from db.session import SessionLocal
    from comfyui.client import map_enhance_submit_error
    from trace_bus import extract_enhance_trace, push_trace

    db = SessionLocal()
    try:
        task = db.get(Task, task_id)
        if not task_is_writable(task):
            return
        task.status = "processing"
        task.error = None
        db.commit()

        user = db.get(User, user_id)
        if not user:
            raise ValueError("用户不存在")

        comfy_prompt_id, _client_id, workflow, comfy_node_url = (
            await comfyui.submit_seedvr2_image_enhance_prompt(
                image_url,
                db=db,
                user=user,
                upscale_factor=seedvr2_params["upscale_factor"],
                strength=seedvr2_params["strength"],
                input_noise_scale=seedvr2_params["input_noise_scale"],
                color_correction=seedvr2_params["color_correction"],
                model_size=seedvr2_params["model_size"],
                client_id=client_id,
            )
        )

        task = db.get(Task, task_id)
        if not task_is_writable(task):
            return

        workflow_trace = extract_enhance_trace(workflow, IMAGE_ENHANCE_SEEDVR2_ID)
        workflow_trace["trace_id"] = trace_id
        workflow_trace["media_type"] = "image"
        await push_trace(4, "WORKFLOW", workflow_trace)

        _assign_comfy_submission(
            task,
            comfy_prompt_id=comfy_prompt_id,
            node_url=comfy_node_url,
        )
        task.status = "pending"
        task.error = None
        db.commit()
        tasks_cache.invalidate_tasks_cache()
    except Exception as e:
        err: str
        if isinstance(e, ValueError):
            err = map_enhance_submit_error(str(e))
        elif isinstance(e, httpx.ConnectError):
            err = "ComfyUI 服务未启动，请先启动 ComfyUI"
        elif isinstance(e, httpx.HTTPStatusError):
            err = f"ComfyUI 返回错误: {e.response.status_code}"
        else:
            err = f"提交失败: {e}"
        task = db.get(Task, task_id)
        if task and task.status != "cancelled":
            _mark_task_terminal(task, status="failed", error=err)
            if not comfy_id_counts_as_executed(task):
                refund_quota(db, user_id, "image", 1)
            db.commit()
            tasks_cache.invalidate_tasks_cache()
        logger.exception("image-enhance submit async failed task_id=%s", task_id)
    finally:
        db.close()


@router.post("/api/tasks/image-enhance")
async def canvas_image_enhance_task(
    body: ImageEnhanceRequest,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """画布静帧 SeedVR2 画质增强。"""
    image_url = (body.image_url or "").strip()
    if not image_url:
        raise HTTPException(status_code=400, detail="图片地址不能为空")

    upscale_factor = body.upscale_factor
    if upscale_factor not in (1.0, 1.5, 2.0, 3.0):
        raise HTTPException(
            status_code=400,
            detail="超分倍数仅支持 1.0 / 1.5 / 2.0 / 3.0",
        )

    from services.video_enhance_recommend import normalize_enhance_params

    seedvr2_params = normalize_enhance_params(
        {
            "upscale_factor": upscale_factor,
            "strength": body.strength,
            "input_noise_scale": body.input_noise_scale,
            "batch_size": 1,
            "color_correction": body.color_correction,
            "model_size": body.model_size,
        }
    )

    row = db.get(RegisteredModel, IMAGE_ENHANCE_SEEDVR2_ID)
    if not row or not row.enabled:
        raise HTTPException(status_code=503, detail="SeedVR2 图像增强未启用")

    await _release_stale_node_tasks_async(db, body.node_id, user.id)
    await reconcile_active_tasks_from_comfyui(db, user.id)
    await check_concurrent_generations(db, user, slots_needed=1, team_id=body.team_id)

    try:
        check_and_consume(db, user.id, "image")
    except QuotaExceededError as e:
        _release_acquired_slots(user.id, team_id=body.team_id, slots=1)
        raise HTTPException(status_code=429, detail=e.message) from e

    trace_id = (body.trace_id or "").strip() or str(uuid.uuid4())
    task_id = str(uuid.uuid4())
    create_task_record(
        db,
        task_id,
        "image",
        "pending",
        user_id=user.id,
        team_id=body.team_id,
        prompt_text=f"image_enhance x{seedvr2_params['upscale_factor']}",
        comfyui_prompt_id=None,
        node_id=body.node_id,
        model_id=IMAGE_ENHANCE_SEEDVR2_ID,
        generation_params=build_image_generation_params(
            ratio=None,
            quality=None,
            width=0,
            height=0,
            mock=False,
            project_id=body.project_id,
        ),
    )
    db.commit()
    tasks_cache.invalidate_tasks_cache()

    if settings.agent_mock_generation:
        asyncio.create_task(
            mock_generation.run_mock_image_task(task_id, [], settings.agent_mock_failure_rate)
        )
        return {"task_id": task_id, "status": "pending"}

    asyncio.create_task(
        _run_image_enhance_submit_task(
            task_id,
            user_id=user.id,
            team_id=body.team_id,
            image_url=image_url,
            seedvr2_params=seedvr2_params,
            client_id=body.client_id,
            trace_id=trace_id,
        )
    )
    return {"task_id": task_id, "status": "pending"}


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
        trace_id=body.trace_id,
    )
    if not task_id:
        raise HTTPException(status_code=400, detail="无法创建 LUT 任务")
    return {"task_id": task_id, "status": "pending"}
