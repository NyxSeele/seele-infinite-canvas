"""qwen_vision：画风参考等帧级视觉描述。"""

from __future__ import annotations

import logging
from pathlib import Path

from services.llm_vision import (
    CONFIGURED_VISION_LLM_ERROR,
    build_vision_user_content,
    invoke_configured_vision_llm,
)

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
    import base64

    b64 = base64.b64encode(data).decode("ascii")
    return f"data:{mime};base64,{b64}"


async def describe_frame_vl(image_path: Path) -> str:
    data_uri = _image_to_data_uri(image_path)
    last_error: Exception | None = None

    for format_hint in ("openai", "dashscope"):
        user_content = build_vision_user_content(
            _FRAME_PROMPT,
            data_uri,
            format_hint=format_hint,
        )
        try:
            content, _, model_id = await invoke_configured_vision_llm(
                "",
                user_content,
                max_tokens=512,
                temperature=0.3,
            )
        except Exception as exc:
            last_error = exc
            logger.warning(
                "视觉帧分析失败 model=%s format=%s err=%s",
                "unknown",
                format_hint,
                exc,
            )
            continue
        if content:
            return content
        last_error = RuntimeError(f"视觉模型 {model_id} 未返回有效描述")

    if last_error and CONFIGURED_VISION_LLM_ERROR in str(last_error):
        raise RuntimeError(CONFIGURED_VISION_LLM_ERROR) from last_error
    if last_error:
        raise RuntimeError(f"视觉模型分析失败: {last_error}") from last_error
    raise RuntimeError("视觉模型分析失败")
