"""多模态帧分析（风格参考抽帧），仅走 Admin 已注册文本模型。"""

from __future__ import annotations

import base64
import logging
from pathlib import Path

from services.qwen import CONFIGURED_LLM_ERROR, invoke_configured_text_llm

logger = logging.getLogger(__name__)

_FRAME_PROMPT = (
    "Describe this film/video frame in concise English. Focus on: color tone, "
    "lighting style, shot composition, camera distance, depth of field, and mood. "
    "Output 2-4 short sentences, no markdown."
)


def _image_to_data_uri(path: Path) -> str:
    data = path.read_bytes()
    suffix = path.suffix.lower()
    mime = "image/jpeg" if suffix in (".jpg", ".jpeg") else "image/png"
    b64 = base64.b64encode(data).decode("ascii")
    return f"data:{mime};base64,{b64}"


async def describe_frame_vl(image_path: Path) -> str:
    data_uri = _image_to_data_uri(image_path)
    user_content = [
        {"type": "image_url", "image_url": {"url": data_uri}},
        {"type": "text", "text": _FRAME_PROMPT},
    ]
    try:
        content, _, model_id = await invoke_configured_text_llm(
            "",
            user_content,
            max_tokens=512,
            temperature=0.3,
        )
    except Exception as exc:
        logger.warning("视觉帧分析失败 model=%s err=%s", "unknown", exc)
        if CONFIGURED_LLM_ERROR in str(exc):
            raise RuntimeError(CONFIGURED_LLM_ERROR) from exc
        raise RuntimeError(f"视觉模型分析失败: {exc}") from exc

    if not content:
        raise RuntimeError(f"视觉模型 {model_id} 未返回有效描述")
    return content
