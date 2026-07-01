import json
import os

import httpx
from openai import AsyncOpenAI

from core.config import settings

DASHSCOPE_BASE_URL = "https://dashscope.aliyuncs.com/compatible-mode/v1"

IMAGE_SYSTEM_PROMPT = """你是专业AI图像生成提示词专家。
把用户的中文描述转成高质量英文提示词。
添加画质词：masterpiece, best quality, highly detailed, sharp focus
根据内容补充合适的风格和场景描述词。
只返回JSON，不要其他内容：
{"positive": "英文正向提示词", "negative": "英文负向提示词"}"""

VIDEO_SYSTEM_PROMPT = """你是专业AI视频生成提示词专家。
把用户的中文描述转成适合视频生成的英文提示词。
添加动态词：smooth motion, cinematic, fluid movement
添加画质词：high quality, detailed
只返回JSON，不要其他内容：
{"positive": "英文正向提示词", "negative": "英文负向提示词"}"""

TRANSLATE_PLAIN_SYSTEM = (
    "You translate Chinese to English for AI image/video generation. "
    "Output only the English prompt text. No quotes, no JSON, no explanation."
)


async def translate_to_english(user_input: str) -> dict:
    """纯文本英译（不依赖 JSON），供 L3 翻译回退。"""
    text = (user_input or "").strip()
    if not text:
        return {"positive": user_input, "error": "empty input"}

    api_key = settings.dashscope_api_key or os.environ.get("DASHSCOPE_API_KEY")
    if not api_key:
        return {"positive": text, "error": "未配置 DASHSCOPE_API_KEY"}

    try:
        async with httpx.AsyncClient(trust_env=False, timeout=30.0) as http:
            async with AsyncOpenAI(
                api_key=api_key,
                base_url=DASHSCOPE_BASE_URL,
                timeout=30.0,
                http_client=http,
            ) as client:
                response = await client.chat.completions.create(
                    model="qwen-plus",
                    messages=[
                        {"role": "system", "content": TRANSLATE_PLAIN_SYSTEM},
                        {"role": "user", "content": text},
                    ],
                    temperature=0.3,
                    max_tokens=500,
                )

        translated = (response.choices[0].message.content or "").strip()
        translated = translated.strip("\"'")
        if not translated:
            raise ValueError("empty translation")
        return {"positive": translated, "error": None}
    except Exception as exc:
        return {
            "positive": text,
            "error": f"翻译失败: {str(exc)[:120]}",
        }


async def optimize_prompt(user_input: str, mode: str = "image") -> dict:
    text = (user_input or "").strip()
    if not text:
        return {
            "positive": user_input,
            "negative": "worst quality, low quality, blurry",
        }

    api_key = settings.dashscope_api_key or os.environ.get("DASHSCOPE_API_KEY")
    if not api_key:
        return {
            "positive": text,
            "negative": "worst quality, low quality, blurry",
            "error": "未配置 DASHSCOPE_API_KEY",
        }

    system_prompt = IMAGE_SYSTEM_PROMPT if mode == "image" else VIDEO_SYSTEM_PROMPT

    try:
        async with httpx.AsyncClient(trust_env=False, timeout=30.0) as http:
            async with AsyncOpenAI(
                api_key=api_key,
                base_url=DASHSCOPE_BASE_URL,
                timeout=30.0,
                http_client=http,
            ) as client:
                response = await client.chat.completions.create(
                    model="qwen3.5-122b-a10b",
                    messages=[
                        {"role": "system", "content": system_prompt},
                        {"role": "user", "content": text},
                    ],
                    temperature=0.7,
                    max_tokens=500,
                )

        result_text = (response.choices[0].message.content or "").strip()
        result_text = result_text.replace("```json", "").replace("```", "").strip()

        result = json.loads(result_text)
        positive = (result.get("positive") or "").strip()
        negative = (result.get("negative") or "").strip()
        if not positive:
            raise ValueError("empty positive")
        return {
            "positive": positive,
            "negative": negative or "worst quality, low quality, blurry",
        }

    except json.JSONDecodeError:
        return {
            "positive": text,
            "negative": "worst quality, low quality, blurry",
            "error": "解析失败，已使用原始描述",
        }
    except Exception as e:
        return {
            "positive": user_input,
            "negative": "worst quality, low quality, blurry",
            "error": f"提示词优化暂时不可用: {str(e)[:100]}",
        }
