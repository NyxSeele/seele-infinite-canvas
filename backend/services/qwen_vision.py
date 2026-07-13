"""DashScope Qwen-VL 多模态调用（风格参考抽帧分析）。"""

from __future__ import annotations

import base64
import logging
from pathlib import Path

from openai import AsyncOpenAI
import httpx

from core.config import settings

logger = logging.getLogger(__name__)

DASHSCOPE_BASE_URL = "https://dashscope.aliyuncs.com/compatible-mode/v1"
VL_MODEL = "qwen-vl-max"

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
    api_key = (settings.dashscope_api_key or "").strip()
    if not api_key:
        raise RuntimeError("未配置 DASHSCOPE_API_KEY，无法分析视频风格")

    data_uri = _image_to_data_uri(image_path)
    llm_timeout = float(settings.llm_http_timeout)
    async with httpx.AsyncClient(trust_env=False, timeout=llm_timeout) as http:
        client = AsyncOpenAI(
            api_key=api_key,
            base_url=DASHSCOPE_BASE_URL,
            timeout=llm_timeout,
            http_client=http,
        )
        response = await client.chat.completions.create(
            model=VL_MODEL,
            messages=[
                {
                    "role": "user",
                    "content": [
                        {"type": "image_url", "image_url": {"url": data_uri}},
                        {"type": "text", "text": _FRAME_PROMPT},
                    ],
                }
            ],
            max_tokens=512,
        )
    content = (response.choices[0].message.content or "").strip()
    if not content:
        raise RuntimeError("视觉模型未返回有效描述")
    return content
