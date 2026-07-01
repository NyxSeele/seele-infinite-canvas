"""分镜表：规则版 + 可选 LLM 扩写三层 prompt 包"""

from __future__ import annotations

import json
import re

from services.qwen import _call_llm

_SYSTEM = """你是专业影视分镜与 AI 视频提示词编剧。
根据用户提供的结构化分镜信息，输出 JSON（不要 markdown 代码块）：
{
  "basic": "【基础设定】段落全文",
  "atmosphere": "【氛围与画质】段落全文",
  "frames": "【画面内容】段落全文，含分镜时间轴",
  "full_text": "三段合并"
}
要求：中文；画面内容按时间轴写清景别运镜动作；避免与基础设定重复堆砌；适合 Seedance/可灵类视频模型。"""


from services.entity_refs import entity_lines_for_prompt
from services.style_reference_service import format_style_for_prompt


def _rule_package(payload: dict) -> dict:
    row = payload.get("row") or {}
    cast = [c for c in (payload.get("cast_library") or []) if c.get("type") != "scene"]
    scene_lib = payload.get("scene_library") or []
    kf_id = payload.get("keyframe_id")

    shot = (row.get("prompt") or row.get("description") or "").strip()
    duration = row.get("duration") or 8
    shot_no = row.get("shot_number") or 1
    sound = (row.get("sound_note") or "").strip() or "无背景音乐，保留必要环境音效"
    atmosphere_note = (row.get("atmosphere_note") or "").strip()
    style_ref = payload.get("style_reference")

    cast_text = entity_lines_for_prompt(cast, scene_lib, row)

    director_keys = [
        ("camera", "景别"),
        ("movement", "运镜"),
        ("lighting", "光影"),
        ("composition", "构图"),
        ("color_grade", "色调"),
        ("lens", "镜头"),
        ("performance", "表演"),
        ("sound_design", "声音"),
    ]
    dir_lines = []
    if atmosphere_note:
        dir_lines.append(f"画质风格：{atmosphere_note}")
    style_block = format_style_for_prompt(style_ref if isinstance(style_ref, dict) else None)
    if style_block:
        dir_lines.append(style_block)
    for key, label in director_keys:
        v = (row.get(key) or "").strip()
        if v:
            dir_lines.append(f"{label}：{v}")
    director_text = "\n".join(dir_lines) if dir_lines else "（可应用画质预设）"

    keyframes = row.get("keyframes") or []
    if kf_id:
        keyframes = [k for k in keyframes if k.get("id") == kf_id]

    frame_parts = []
    for i, kf in enumerate(keyframes):
        label = (kf.get("label") or f"格{i + 1}").strip()
        start = kf.get("time_start", 0)
        end = kf.get("time_end", 0)
        time_s = f"{start}s–{end}s" if end > start else f"{start}s"
        text = (kf.get("prompt") or kf.get("description") or "").strip() or "（待填写）"
        frame_parts.append(
            f"分镜{i + 1}（{time_s}）· {label}\n{text}"
        )
    frames_text = "\n\n".join(frame_parts) if frame_parts else "（暂无分镜格）"

    basic = "\n".join(
        [
            "【基础设定】",
            f"镜号：{shot_no} · 时长：{duration} 秒",
            f"剧情/主体：{shot or '（待填写）'}",
            cast_text,
            f"声音：{sound}",
        ]
    )
    atmosphere = "【氛围与画质】\n" + director_text
    frames = "【画面内容】\n" + frames_text
    full_text = f"{basic}\n\n{atmosphere}\n\n{frames}"

    api_parts = [shot] if shot else []
    for kf in keyframes:
        t = (kf.get("prompt") or kf.get("description") or "").strip()
        if not t:
            continue
        label = kf.get("label") or "格"
        start = kf.get("time_start", 0)
        end = kf.get("time_end", 0)
        time_s = f"{start}s–{end}s" if end > start else f"{start}s"
        api_parts.append(f"【{time_s} {label}】{t}")
    api_description = "；".join(api_parts)

    return {
        "basic": basic,
        "atmosphere": atmosphere,
        "frames": frames,
        "full_text": full_text,
        "api_description": api_description,
        "source": "rule",
    }


def _parse_llm_json(raw: str) -> dict | None:
    text = (raw or "").strip()
    if not text:
        return None
    if text.startswith("```"):
        text = re.sub(r"^```(?:json)?\s*", "", text)
        text = re.sub(r"\s*```$", "", text)
    try:
        data = json.loads(text)
        if isinstance(data, dict) and data.get("full_text"):
            return data
    except json.JSONDecodeError:
        pass
    return None


async def build_shot_prompt_package(payload: dict, *, use_llm: bool = True) -> dict:
    rule = _rule_package(payload)
    if not use_llm:
        return rule

    try:
        user_prompt = json.dumps(payload, ensure_ascii=False, indent=2)
        raw, _ = await _call_llm(_SYSTEM, user_prompt, max_tokens=3500)
        parsed = _parse_llm_json(raw)
        if parsed:
            full = parsed.get("full_text") or rule["full_text"]
            return {
                "basic": parsed.get("basic") or rule["basic"],
                "atmosphere": parsed.get("atmosphere") or rule["atmosphere"],
                "frames": parsed.get("frames") or rule["frames"],
                "full_text": full,
                "api_description": rule["api_description"],
                "source": "llm",
            }
    except Exception:
        pass

    return rule
