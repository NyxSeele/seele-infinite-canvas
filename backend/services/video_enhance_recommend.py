"""视频画质增强：LLM / 规则参数推荐。"""

from __future__ import annotations

import json
import logging
from typing import Any

from services.qwen import _call_llm, clean_json_response

logger = logging.getLogger(__name__)

VALID_UPSCALE = (1.0, 1.5, 2.0, 3.0)
VALID_BATCH = (4, 8, 16)
VALID_COLOR = ("lab", "none")
VALID_MODEL_SIZE = ("3b", "7b")
VALID_STRENGTH = ("normal", "sharp")

_RECOMMEND_SYSTEM = """你是 AI 短视频画质增强参数顾问。用户视频均为 AI Studio 生成的短剧片段，目标是提升画质后发布到短视频平台。

只输出 JSON，不要 markdown 或解释文字：
{
  "upscale_factor": 2.0,
  "model_variant": "fp16",
  "input_noise_scale": 0.25,
  "batch_size": 8,
  "color_correction": "lab",
  "model_size": "7b",
  "strength": "normal",
  "reasoning": "一行中文说明推荐理由"
}

参数范围：
- upscale_factor: 1.0 | 1.5 | 2.0 | 3.0（1.0=仅去噪增强不超分）
- input_noise_scale: 0.0–1.0，步长 0.05；AI 生成写实内容建议 0.25
- batch_size: 4 | 8 | 16
- color_correction: "lab" | "none"
- model_size: "3b" | "7b"
- strength: "normal" | "sharp"
- model_variant: 固定 "fp16"

推荐逻辑：
- 分辨率短边 ≤720 → upscale_factor 2.0；720–1080 → 1.5；已 ≥1080 → 1.0
- source_type 为 ai_generated → input_noise_scale 0.25
- duration ≤5s → batch_size 16；5–15s → 8；>15s → 4
- 默认 color_correction lab、model_size 7b、strength normal"""

_CINEMATIC_RECOMMEND_APPEND = (
    "\n\n当 content_style 为 photorealistic_cinema 时："
    "内容为真人写实风格，优先保留皮肤纹理和自然细节，避免过度锐化或磨皮；"
    "input_noise_scale 建议 0.15；若短边 ≤1080 优先 upscale_factor 2.0（目标 4K）。"
)


def _is_cinematic(content_style: str | None) -> bool:
    return (content_style or "").strip() != "generic"


def _apply_cinematic_param_overrides(
    params: dict[str, Any],
    video_info: dict[str, Any],
    *,
    content_style: str = "generic",
) -> dict[str, Any]:
    if not _is_cinematic(content_style):
        return params
    out = dict(params)
    out["input_noise_scale"] = 0.15
    width = int(video_info.get("width") or 1280)
    height = int(video_info.get("height") or 720)
    if min(width, height) <= 1080:
        out["upscale_factor"] = 2.0
    return normalize_enhance_params(out)


def _snap_upscale(value: float) -> float:
    try:
        v = float(value)
    except (TypeError, ValueError):
        return 2.0
    if v <= 1.0:
        return 1.0
    if v <= 1.5:
        return 1.5
    if v <= 2.0:
        return 2.0
    return 3.0


def _snap_batch(value: int) -> int:
    try:
        v = int(value)
    except (TypeError, ValueError):
        return 8
    if v <= 4:
        return 4
    if v <= 8:
        return 8
    return 16


def normalize_enhance_params(raw: dict[str, Any] | None) -> dict[str, Any]:
    """校验并钳制推荐/请求参数为合法值。"""
    data = raw or {}
    noise = data.get("input_noise_scale", 0.25)
    try:
        noise = float(noise)
    except (TypeError, ValueError):
        noise = 0.25
    noise = max(0.0, min(1.0, round(noise / 0.05) * 0.05))

    strength = str(data.get("strength") or "normal").strip().lower()
    if strength not in VALID_STRENGTH:
        strength = "normal"

    color = str(data.get("color_correction") or "lab").strip().lower()
    if color not in VALID_COLOR:
        color = "lab"

    model_size = str(data.get("model_size") or "7b").strip().lower()
    if model_size not in VALID_MODEL_SIZE:
        model_size = "7b"

    return {
        "upscale_factor": _snap_upscale(data.get("upscale_factor", 2.0)),
        "model_variant": "fp16",
        "input_noise_scale": noise,
        "batch_size": _snap_batch(data.get("batch_size", 8)),
        "color_correction": color,
        "model_size": model_size,
        "strength": strength,
    }


def _rule_recommend_params(
    video_info: dict[str, Any],
    *,
    content_style: str = "generic",
) -> tuple[dict[str, Any], str]:
    width = int(video_info.get("width") or 1280)
    height = int(video_info.get("height") or 720)
    duration = float(video_info.get("duration") or 5.0)
    short_side = min(width, height)
    cinematic = _is_cinematic(content_style)

    if cinematic and short_side <= 1080:
        upscale = 2.0
        reason_scale = "写实电影模式，目标 4K，建议 2 倍超分"
    elif short_side >= 1080:
        upscale = 1.0
        reason_scale = "已达 1080p+，建议仅增强不去噪超分"
    elif short_side >= 720:
        upscale = 1.5
        reason_scale = "720p–1080p，建议 1.5 倍超分"
    else:
        upscale = 2.0
        reason_scale = "720p 以下，建议 2 倍超分"

    if duration <= 5:
        batch = 16
    elif duration <= 15:
        batch = 8
    else:
        batch = 4

    noise = 0.15 if cinematic else 0.25

    params = normalize_enhance_params(
        {
            "upscale_factor": upscale,
            "input_noise_scale": noise,
            "batch_size": batch,
            "color_correction": "lab",
            "model_size": "7b",
            "strength": "normal",
        }
    )
    prefix = "写实电影 AI 推荐：" if cinematic else "AI 推荐："
    reasoning = f"{prefix}{reason_scale}；时长 {duration:.1f}s 批次 {batch}"
    return params, reasoning


async def recommend_enhance_params(
    video_info: dict[str, Any],
    *,
    use_llm: bool = True,
    content_style: str = "generic",
) -> tuple[dict[str, Any], str]:
    """LLM 推荐参数；失败时回退规则推荐。"""
    if not use_llm:
        params, reasoning = _rule_recommend_params(
            video_info, content_style=content_style
        )
        return _apply_cinematic_param_overrides(
            params, video_info, content_style=content_style
        ), reasoning

    system = _RECOMMEND_SYSTEM
    if _is_cinematic(content_style):
        system = system + _CINEMATIC_RECOMMEND_APPEND
    payload = {**video_info, "content_style": content_style}
    user_prompt = json.dumps(payload, ensure_ascii=False)
    try:
        raw, _ = await _call_llm(system, user_prompt, max_tokens=800)
        parsed = json.loads(clean_json_response(raw))
        reasoning = str(parsed.pop("reasoning", "") or "").strip()
        params = normalize_enhance_params(parsed)
        params = _apply_cinematic_param_overrides(
            params, video_info, content_style=content_style
        )
        if not reasoning:
            _, reasoning = _rule_recommend_params(
                video_info, content_style=content_style
            )
        return params, reasoning
    except Exception as exc:
        logger.warning("video enhance LLM recommend failed, using rules: %s", exc)
        params, reasoning = _rule_recommend_params(
            video_info, content_style=content_style
        )
        return _apply_cinematic_param_overrides(
            params, video_info, content_style=content_style
        ), reasoning
