"""
千问 DashScope（兼容 OpenAI 接口）文本生成。
"""

import os

from openai import AsyncOpenAI

from db.base import SessionLocal
from model_registry import MODEL_MAP
from models import RegisteredModel
from services.registered_model_utils import normalize_openai_compatible_base, resolve_api_model_name
from services.api_key_service import get_registered_model_api_key


async def call_openai_compatible(model_id: str, prompt: str, max_tokens: int = 1000) -> str:
    """
    通用 OpenAI-compatible 调用函数，适用于千问及其他兼容 OpenAI 协议的接口。
    从 registered_models 表读取 api_key、api_base、model_string。
    """
    db = SessionLocal()
    try:
        row = (
            db.query(RegisteredModel)
            .filter(RegisteredModel.id == model_id, RegisteredModel.enabled.is_(True))
            .first()
        )
        api_key = get_registered_model_api_key(row)
        if not api_key and row:
            preset = MODEL_MAP.get(model_id) or {}
            env_name = preset.get("api_key_env")
            if env_name:
                api_key = (os.environ.get(env_name) or "").strip() or None
        if not row or not api_key:
            raise ValueError(f"模型 {model_id} 未配置或未启用")
        if not (row.api_base or "").strip():
            raise ValueError(f"模型 {model_id} 未配置 API Base")

        client = AsyncOpenAI(
            api_key=api_key,
            base_url=normalize_openai_compatible_base(row.api_base.strip()),
        )
        response = await client.chat.completions.create(
            model=resolve_api_model_name(
                row.id, row.model_string, display_name=row.display_name
            ),
            messages=[{"role": "user", "content": prompt}],
            max_tokens=max_tokens,
        )
        return response.choices[0].message.content or ""
    finally:
        db.close()


async def call_qwen(model_id: str, prompt: str, max_tokens: int = 1000) -> str:
    """兼容旧调用名。"""
    return await call_openai_compatible(model_id=model_id, prompt=prompt, max_tokens=max_tokens)
