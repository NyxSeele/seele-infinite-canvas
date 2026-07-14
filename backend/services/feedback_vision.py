"""Fetch task result media for LLM vision analysis."""

from __future__ import annotations

import base64
import json
import logging
import os
import shutil
import subprocess
import tempfile
from pathlib import Path
from urllib.parse import urlparse

import httpx

from comfyui import client as comfyui
from services import mock_generation
from services.media_access import (
    append_media_ticket,
    grant_output_access,
    issue_media_ticket,
    normalize_media_reference_url,
)
from services.task_generation_params import parse_generation_params

logger = logging.getLogger(__name__)

_VISION_SAMPLE_LIMIT = 8
_UNSATISFIED_LIMIT = 6
_SATISFIED_LIMIT = 2
_CAPTION_PROMPT_MAX = 400


def _local_api_base() -> str:
    port = int(os.environ.get("PORT", "7788"))
    return f"http://127.0.0.1:{port}"


def _resolve_fetch_url(result: str, admin_user_id: int) -> str:
    raw = (result or "").strip()
    if not raw:
        return ""
    if raw.startswith("http://") or raw.startswith("https://"):
        return raw
    path = normalize_media_reference_url(raw)
    if not path.startswith("/"):
        path = f"/{path}"
    grant_output_access(admin_user_id, path)
    ticket = issue_media_ticket(admin_user_id)["media_ticket"]
    signed = append_media_ticket(path, ticket)
    return f"{_local_api_base()}{signed}"


def _guess_media_kind(task_type: str, url: str) -> str:
    if task_type == "video":
        return "video"
    lower = url.lower()
    if any(lower.endswith(ext) for ext in (".mp4", ".webm", ".mov", ".mkv")):
        return "video"
    return "image"


def _image_mime_from_url(url: str) -> str:
    path = urlparse(url).path
    mime = comfyui.guess_media_type(path, fallback="image/jpeg")
    if mime.startswith("image/"):
        return mime
    return "image/jpeg"


def _format_params_summary(params: dict) -> str:
    if not params:
        return "—"
    parts: list[str] = []
    for key in ("ratio", "quality", "resolution", "duration", "mode", "width", "height"):
        value = params.get(key)
        if value is not None and value != "":
            parts.append(f"{key}={value}")
    if params.get("has_reference"):
        parts.append(f"reference_count={params.get('reference_count', 1)}")
    return " · ".join(parts) if parts else "—"


def _parse_rating_tags(task) -> list[str]:
    raw = getattr(task, "rating_tags", None)
    if not raw:
        return []
    try:
        data = json.loads(raw)
        if isinstance(data, list):
            return [str(x) for x in data if x]
    except (json.JSONDecodeError, TypeError):
        pass
    return []


def _is_mock_task(task) -> bool:
    if task.comfyui_prompt_id == mock_generation.MOCK_PROMPT_ID:
        return True
    params = parse_generation_params(task.generation_params)
    return bool(params.get("mock"))


def _is_eligible_task(task) -> bool:
    if not (task.result or "").strip():
        return False
    if _is_mock_task(task):
        return False
    return task.user_rating in (0, 1)


def _effective_model_id(task) -> str:
    if task.model_id:
        return task.model_id
    if task.video_backend:
        return task.video_backend
    return "unknown"


def _build_caption(task, model_key: str) -> str:
    rating_label = "满意" if task.user_rating == 1 else "不满意"
    tags = _parse_rating_tags(task)
    params = parse_generation_params(task.generation_params)
    original = (task.original_input or "")[:_CAPTION_PROMPT_MAX]
    compiled = (task.compiled_prompt or "")[:_CAPTION_PROMPT_MAX]
    comment = (task.rating_comment or "")[:200]
    lines = [
        f"【样本 task_id={task.id}】",
        f"模型: {model_key} | 类型: {task.task_type} | 评价: {rating_label}",
        f"标签: {', '.join(tags) if tags else '无'}",
        f"参数: {_format_params_summary(params)}",
        f"原始输入: {original or '—'}",
        f"编译后 prompt: {compiled or '—'}",
    ]
    if comment:
        lines.append(f"用户补充: {comment}")
    lines.append("（下图/本帧为该样本的生成结果，请对照上文 prompt 分析）")
    return "\n".join(lines)


def _extract_video_frame(video_bytes: bytes) -> tuple[bytes, str] | None:
    ffmpeg = shutil.which("ffmpeg")
    if not ffmpeg:
        return None
    with tempfile.TemporaryDirectory() as tmp:
        inp = Path(tmp) / "input.mp4"
        out = Path(tmp) / "frame.jpg"
        inp.write_bytes(video_bytes)
        try:
            subprocess.run(
                [ffmpeg, "-y", "-ss", "1", "-i", str(inp), "-frames:v", "1", str(out)],
                check=True,
                capture_output=True,
                timeout=30,
            )
        except (subprocess.CalledProcessError, subprocess.TimeoutExpired) as exc:
            logger.warning("ffmpeg frame extract failed: %s", exc)
            return None
        if not out.exists():
            return None
        return out.read_bytes(), "image/jpeg"


async def _download_bytes(url: str) -> bytes | None:
    try:
        async with httpx.AsyncClient(timeout=60.0, follow_redirects=True) as client:
            resp = await client.get(url)
            resp.raise_for_status()
            return resp.content
    except httpx.HTTPError as exc:
        logger.warning("vision media download failed url=%s err=%s", url[:120], exc)
        return None


def _to_image_block(data: bytes, media_type: str) -> dict:
    b64 = base64.standard_b64encode(data).decode("ascii")
    return {
        "type": "image",
        "source": {
            "type": "base64",
            "media_type": media_type,
            "data": b64,
        },
    }


def _to_text_block(text: str) -> dict:
    return {"type": "text", "text": text}


def _select_tasks_for_vision(tasks: list) -> list:
    unsatisfied: list = []
    satisfied: list = []
    for task in tasks:
        if not _is_eligible_task(task):
            continue
        if task.user_rating == 0:
            unsatisfied.append(task)
        else:
            satisfied.append(task)

    selected: list = []
    seen_models: set[str] = set()

    for task in unsatisfied:
        if len(selected) >= _UNSATISFIED_LIMIT:
            break
        model_key = _effective_model_id(task)
        if model_key in seen_models and len(seen_models) >= 4:
            continue
        selected.append(task)
        seen_models.add(model_key)

    if len(selected) < _UNSATISFIED_LIMIT:
        for task in unsatisfied:
            if task in selected:
                continue
            if len(selected) >= _UNSATISFIED_LIMIT:
                break
            selected.append(task)

    satisfied_picked: list = []
    satisfied_models: set[str] = set()
    for task in satisfied:
        if len(satisfied_picked) >= _SATISFIED_LIMIT:
            break
        model_key = _effective_model_id(task)
        if model_key in satisfied_models and len(satisfied_picked) >= 1:
            continue
        satisfied_picked.append(task)
        satisfied_models.add(model_key)

    if len(satisfied_picked) < _SATISFIED_LIMIT:
        for task in satisfied:
            if task in satisfied_picked:
                continue
            if len(satisfied_picked) >= _SATISFIED_LIMIT:
                break
            satisfied_picked.append(task)

    combined = selected + satisfied_picked
    return combined[:_VISION_SAMPLE_LIMIT]


async def build_vision_samples(tasks: list, admin_user_id: int) -> tuple[list[dict], list[dict]]:
    """Return (llm_content_blocks, metadata_list).

    Each sample is a caption text block followed by an image block (Anthropic-style;
    converted to OpenAI multimodal at call time).
    """
    blocks: list[dict] = []
    meta: list[dict] = []
    candidates = _select_tasks_for_vision(tasks)

    for task in candidates:
        model_key = _effective_model_id(task)
        fetch_url = _resolve_fetch_url(task.result, admin_user_id)
        if not fetch_url:
            meta.append(
                {
                    "task_id": task.id,
                    "model_id": model_key,
                    "user_rating": task.user_rating,
                    "vision": "skipped",
                    "reason": "empty_fetch_url",
                }
            )
            continue

        raw_bytes = await _download_bytes(fetch_url)
        if not raw_bytes:
            meta.append(
                {
                    "task_id": task.id,
                    "model_id": model_key,
                    "user_rating": task.user_rating,
                    "vision": "skipped",
                    "reason": "download_failed",
                }
            )
            continue

        media_kind = _guess_media_kind(task.task_type, fetch_url)
        image_bytes = raw_bytes
        image_type = _image_mime_from_url(fetch_url)
        if media_kind == "video":
            extracted = _extract_video_frame(raw_bytes)
            if not extracted:
                meta.append(
                    {
                        "task_id": task.id,
                        "model_id": model_key,
                        "user_rating": task.user_rating,
                        "vision": "skipped",
                        "reason": "ffmpeg_unavailable_or_failed",
                    }
                )
                continue
            image_bytes, image_type = extracted

        blocks.append(_to_text_block(_build_caption(task, model_key)))
        blocks.append(_to_image_block(image_bytes, image_type))
        meta.append(
            {
                "task_id": task.id,
                "model_id": model_key,
                "user_rating": task.user_rating,
                "vision": "image",
                "task_type": task.task_type,
                "media_type": image_type,
            }
        )

    return blocks, meta
