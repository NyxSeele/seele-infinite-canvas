"""将节点字段聚合为按 workflow_type 区分的最终 prompt（纯文本，不依赖 GPU）。"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Literal

from services.script_shot_strategy import detect_new_subject, new_subject_emphasis
from services.style_reference_service import format_style_for_prompt

WorkflowType = Literal["sd15", "sdxl", "flux"]

MAX_POSITIVE_LENGTH: dict[str, int] = {
    "sd15": 500,
    "sdxl": 600,
    "flux": 512,
}

DEFAULT_NEGATIVE_ZH = "模糊, 低质量, 水印, 文字"
ANIME_NEGATIVE_EN = "photorealistic, realistic, 3D render, photo"
_ANIME_STYLE_KEYS = frozenset({"二次元", "动漫", "2D", "cel"})

VALID_WORKFLOW_TYPES = frozenset(MAX_POSITIVE_LENGTH.keys())

_CAMERA_RE = re.compile(
    r"(特写|近景|中景|全景|远景|俯拍|仰拍|跟拍|推拉|长镜头)"
)

# 常见中文风格 → 英文 tag（供 SD 系模型识别）
STYLE_EN_TAGS: dict[str, str] = {
    "二次元": "anime style, 2D illustration, cel shading",
    "动漫": "anime style, 2D illustration",
    "写实": "photorealistic, realistic photo",
    "电影感": "cinematic lighting, film still",
    "赛博朋克": "cyberpunk style, neon lights",
    "水墨": "chinese ink painting style",
    "油画": "oil painting style",
}


@dataclass(frozen=True)
class BuiltPrompt:
    positive: str
    negative: str
    workflow_type: str
    truncated: bool
    segments: tuple[str, ...]
    display_prompt: str = ""
    parsed_fields: dict | None = None


def normalize_workflow_type(value: str | None) -> str:
    wt = (value or "sd15").strip().lower()
    if wt not in VALID_WORKFLOW_TYPES:
        return "sd15"
    return wt


def _clean(text: str | None) -> str:
    if not text:
        return ""
    return " ".join(str(text).strip().split())


def _format_camera(value: str) -> str:
    v = value.rstrip(".")
    lower = v.lower()
    if "shot" in lower or "angle" in lower or "镜头" in v or "景别" in v:
        return v
    return f"{v} shot"


def _merge_style(field_style: str, global_style: str) -> str:
    parts: list[str] = []
    for raw in (global_style, field_style):
        cleaned = _clean(raw)
        if cleaned and cleaned not in parts:
            parts.append(cleaned)
    return ", ".join(parts)


def resolve_style_en_tags(global_style: str) -> str:
    """将中文风格名映射为 SD 可识别的英文 tag。"""
    style = _clean(global_style)
    if not style:
        return ""
    for zh, en in STYLE_EN_TAGS.items():
        if zh in style:
            return en
    return style


def infer_fields_from_description_rule(text: str) -> dict:
    """规则版：从单句描述推断结构化字段（不依赖 LLM/GPU）。"""
    raw = _clean(text)
    if not raw:
        return {"description": ""}

    camera = ""
    match = _CAMERA_RE.search(raw)
    if match:
        camera = match.group(1)

    return {
        "description": raw,
        "character": "",
        "scene": "",
        "style": "",
        "camera": camera,
        "action": "",
        "lighting": "",
        "extra": "",
        "unwanted": "",
    }


def _build_segments(fields: dict, *, global_style: str = "") -> list[str]:
    description = _clean(fields.get("description"))
    character = _clean(fields.get("character"))
    action = _clean(fields.get("action"))
    scene = _clean(fields.get("scene"))
    style = _merge_style(_clean(fields.get("style")), global_style)
    camera = _clean(fields.get("camera"))
    lighting = _clean(fields.get("lighting"))
    extra = _clean(fields.get("extra"))

    segments: list[str] = []
    if description:
        segments.append(description)
    if character:
        segments.append(character)
    if action:
        segments.append(action)
    if scene:
        segments.append(f"in {scene}" if not scene.lower().startswith("in ") else scene)
    if style:
        segments.append(style)
    if camera:
        segments.append(_format_camera(camera))
    if lighting:
        segments.append(lighting)
    if extra:
        segments.append(extra)
    return segments


def _truncate_positive(text: str, limit: int) -> tuple[str, bool]:
    if len(text) <= limit:
        return text, False
    cut = text[:limit]
    comma = cut.rfind(", ")
    if comma > limit * 0.6:
        return cut[:comma].rstrip(", "), True
    cn_comma = cut.rfind("，")
    if cn_comma > limit * 0.6:
        return cut[:cn_comma].rstrip("，"), True
    return cut.rstrip(", "), True


def _is_anime_style(style: str) -> bool:
    s = _clean(style)
    if not s:
        return False
    return any(key in s for key in _ANIME_STYLE_KEYS)


def _build_negative(
    fields: dict,
    workflow_type: str,
    *,
    global_style: str = "",
) -> str:
    if workflow_type == "flux":
        return ""
    unwanted = _clean(fields.get("unwanted"))
    base = unwanted if unwanted else ""
    zh_part = DEFAULT_NEGATIVE_ZH
    if base:
        parts = [base, zh_part]
    else:
        parts = [zh_part]

    field_style = _clean(fields.get("style"))
    if _is_anime_style(global_style) or _is_anime_style(field_style):
        parts.append(ANIME_NEGATIVE_EN)

    return ", ".join(parts)


def build_prompt_from_fields(
    fields: dict | None,
    workflow_type: str,
    *,
    global_style: str = "",
) -> BuiltPrompt:
    wt = normalize_workflow_type(workflow_type)
    field_map = dict(fields or {})
    segments = _build_segments(field_map, global_style=global_style)
    positive = ", ".join(segments)
    positive, truncated = _truncate_positive(positive, MAX_POSITIVE_LENGTH[wt])
    negative = _build_negative(field_map, wt, global_style=global_style)
    return BuiltPrompt(
        positive=positive,
        negative=negative,
        workflow_type=wt,
        truncated=truncated,
        segments=tuple(segments),
        display_prompt=positive,
        parsed_fields=field_map,
    )


def build_script_shot_prompt(
    description: str,
    workflow_type: str,
    *,
    global_style: str = "",
    theme_context: str = "",
    prior_shots: list[dict] | None = None,
    shot_number: int | None = None,
    continuity_mode: bool = True,
    style_reference: dict | None = None,
) -> BuiltPrompt:
    """
    分镜单行 prompt：UI 只展示用户描述，生成用简洁中文 + 英文风格 tag。

    镜头关联分两层（由 script_shot_strategy 决定视觉层是否 img2img）：
    - 剧情层（continuity_mode）：主题设定 +「承接上一镜头」中文注入 → 供 L3 翻译，统一角色/场景语义
    - 视觉层（visual_continuity）：上一镜成片作 img2img 参考 + denoise，由策略模块单独返回
    """
    wt = normalize_workflow_type(workflow_type)
    desc = _clean(description)
    display = desc

    gen_parts: list[str] = []
    theme = _clean(theme_context)
    style = _clean(global_style)
    style_en = resolve_style_en_tags(style)

    if theme:
        gen_parts.append(theme)

    prior = prior_shots or []
    if continuity_mode and prior and shot_number and shot_number > 1:
        last = prior[-1]
        last_desc = _clean(last.get("description"))
        if last_desc:
            gen_parts.append(f"承接上一镜头：{last_desc}")

    style_ref_block = format_style_for_prompt(style_reference)
    if style_ref_block:
        gen_parts.append(style_ref_block)

    if desc:
        gen_parts.append(desc)

    if continuity_mode and prior and shot_number and shot_number > 1:
        last = prior[-1]
        last_desc = _clean(last.get("description"))
        if last_desc and desc and detect_new_subject(desc, last_desc):
            emphasis = new_subject_emphasis(desc)
            if emphasis:
                gen_parts.append(emphasis)

    if style and style not in desc:
        gen_parts.append(f"{style}风格")

    positive = "，".join(p for p in gen_parts if p)
    if style_en:
        positive = f"{positive}，{style_en}" if positive else style_en

    positive, truncated = _truncate_positive(positive, MAX_POSITIVE_LENGTH[wt])
    negative = _build_negative({}, wt, global_style=style)

    return BuiltPrompt(
        positive=positive,
        negative=negative,
        workflow_type=wt,
        truncated=truncated,
        segments=tuple(gen_parts),
        display_prompt=display,
        parsed_fields={"description": desc, "theme": theme, "style": style},
    )
