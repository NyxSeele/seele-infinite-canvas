"""视觉 / 多模态 LLM 路由（画风参考抽帧、反馈图视等）。"""

from __future__ import annotations

import logging
import re
from typing import Any

from sqlalchemy.orm import Session

from db.session import SessionLocal
from models import RegisteredModel
from services.api_key_service import get_registered_model_api_key
from services.llm_resilience import is_llm_quota_exhausted_error
from services.llm_router import (
    _list_enabled_text_api,
    is_model_quota_exhausted,
    mark_model_quota_exhausted,
    record_usage,
    resolve_text_model,
)
from services.qwen import CONFIGURED_LLM_ERROR, _invoke_chat_completion

logger = logging.getLogger(__name__)

CONFIGURED_VISION_LLM_ERROR = (
    "未配置可用的视觉模型，请在 Admin 启用 qwen-vl-max 等多模态 API 模型"
)

DEFAULT_VISION_MODEL_ID = "qwen-vl-max"
DEFAULT_VISION_MODEL_STRING = "qwen-vl-max"

_VISION_MODEL_RE = re.compile(
    r"(vl[-_]|[-_]vl|vision|gpt-4o|gpt-4-turbo|gemini.*flash|claude-3.*opus|claude-3.*sonnet)",
    re.IGNORECASE,
)


def model_supports_vision(row: RegisteredModel | None) -> bool:
    if not row or row.type != "api" or row.category != "text":
        return False
    blob = " ".join(
        str(part or "")
        for part in (row.id, row.model_string, row.display_name)
    )
    return bool(_VISION_MODEL_RE.search(blob))


def resolve_vision_model_candidates(db: Session | None = None) -> list[RegisteredModel]:
    own = db is None
    if own:
        db = SessionLocal()
    try:
        rows = [
            row
            for row in _list_enabled_text_api(db)
            if model_supports_vision(row) and not is_model_quota_exhausted(row.id)
        ]
        rows.sort(
            key=lambda row: (
                0 if "vl" in (row.model_string or row.id).lower() else 1,
                row.id,
            )
        )
        return rows
    finally:
        if own:
            db.close()


def ensure_vision_model_registered(db: Session | None = None) -> bool:
    """若无已启用的视觉模型，从默认文本 API 复制配置并注册 qwen-vl-max。"""
    own = db is None
    if own:
        db = SessionLocal()
    try:
        if resolve_vision_model_candidates(db):
            return False

        default = resolve_text_model(db)
        if not default or not (default.api_base or "").strip():
            logger.warning("画风视觉模型：无默认文本 API，无法自动注册 qwen-vl-max")
            return False
        if not get_registered_model_api_key(default):
            logger.warning("画风视觉模型：默认文本 API 无 Key，无法自动注册 qwen-vl-max")
            return False

        row = db.get(RegisteredModel, DEFAULT_VISION_MODEL_ID)
        if row is None:
            row = RegisteredModel(
                id=DEFAULT_VISION_MODEL_ID,
                display_name="Qwen VL Max",
                category="text",
                type="api",
                provider=default.provider,
                enabled=True,
            )
            db.add(row)
        row.api_base = default.api_base
        row.api_key = default.api_key
        row.model_string = DEFAULT_VISION_MODEL_STRING
        row.enabled = True
        db.commit()
        logger.info("画风视觉模型：已自动注册并启用 %s", DEFAULT_VISION_MODEL_ID)
        return True
    finally:
        if own:
            db.close()


def build_vision_user_content(
    text: str,
    image_data_uri: str,
    *,
    format_hint: str = "openai",
) -> list[dict[str, Any]]:
    text = (text or "").strip()
    if format_hint == "dashscope":
        return [
            {"image": image_data_uri},
            {"text": text},
        ]
    return [
        {"type": "image_url", "image_url": {"url": image_data_uri}},
        {"type": "text", "text": text},
    ]


async def invoke_configured_vision_llm(
    system_prompt: str,
    user_content: str | list,
    *,
    max_tokens: int = 512,
    temperature: float = 0.3,
    db=None,
) -> tuple[str, str | None, str]:
    candidates = resolve_vision_model_candidates(db)
    if not candidates:
        raise ValueError(CONFIGURED_VISION_LLM_ERROR)

    last_exc: Exception | None = None
    tried: set[str] = set()

    while True:
        row = None
        for candidate in candidates:
            if candidate.id not in tried:
                row = candidate
                break
        if row is None:
            break

        tried.add(row.id)
        api_key = get_registered_model_api_key(row)
        base_url = (row.api_base or "").strip()
        model = (row.model_string or row.id).strip()
        if not api_key or not base_url or not model:
            last_exc = ValueError(f"视觉模型 {row.id} 未配置 API Key 或 API Base")
            continue

        try:
            content, finish, usage = await _invoke_chat_completion(
                api_key=api_key,
                base_url=base_url,
                model=model,
                system_prompt=system_prompt,
                user_content=user_content,
                max_tokens=max_tokens,
                temperature=temperature,
            )
        except Exception as exc:
            last_exc = exc
            if is_llm_quota_exhausted_error(exc):
                mark_model_quota_exhausted(row.id)
                candidates = resolve_vision_model_candidates(db)
                continue
            raise

        total = int(usage.get("total_tokens") or 0)
        if total > 0:
            record_usage(row.id, total)
        if not content:
            last_exc = ValueError("视觉模型返回空内容")
            continue
        return content, finish, row.id

    if last_exc is not None:
        raise last_exc
    raise ValueError(CONFIGURED_VISION_LLM_ERROR or CONFIGURED_LLM_ERROR)
