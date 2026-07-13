"""将节点字段聚合为按 workflow_type 区分的最终 prompt（纯文本，不依赖 GPU）。"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Literal

from services.quality_presets import get_suffixes, normalize_quality_preset_id
from services.script_shot_strategy import detect_new_subject, new_subject_emphasis
from services.style_reference_service import format_style_for_prompt

WorkflowType = Literal["sd15", "sdxl", "flux"]
ModelTarget = Literal["flux", "wan-t2v", "wan-i2v", "seedance"]

SEEDANCE_MIN_WORDS = 30
SEEDANCE_MAX_WORDS = 100
SEEDANCE_MODEL_PARAMS = {
    "steps": 0,
    "cfg": 0,
    "width": 1280,
    "height": 720,
    "fps": 24,
    "prompt_style": "short",
}

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

_MOVEMENT_LABEL_RE = re.compile(r"运镜[：:]\s*([^；;\n]+)")
_CAMERA_LABEL_RE = re.compile(r"景别[：:]\s*([^；;\n]+)")

# G31: 中文运镜 → 英文前置句（Wan L3/compile）
_MOVEMENT_EN = (
    ("缓慢推近", "The camera slowly dollies in"),
    ("缓慢推进", "The camera slowly dollies in"),
    ("推近", "The camera dollies in"),
    ("推进", "The camera dollies in"),
    ("推轨", "The camera dollies forward on a track"),
    ("缓慢拉远", "The camera slowly pulls back"),
    ("拉远", "The camera pulls back"),
    ("拉开", "The camera pulls back"),
    ("横摇", "The camera pans horizontally"),
    ("左右摇", "The camera pans horizontally"),
    ("摇镜", "The camera pans"),
    ("俯摇", "The camera tilts down"),
    ("仰摇", "The camera tilts up"),
    ("跟拍", "The camera follows the subject"),
    ("环绕", "The camera orbits around the subject"),
    ("固定", "Static shot, locked-off camera"),
    ("稳定运镜", "Smooth stabilized camera move"),
)

_CAMERA_EN = (
    ("特写", "close-up shot"),
    ("近景", "close shot"),
    ("中景", "medium shot"),
    ("全景", "wide shot"),
    ("远景", "extreme wide shot"),
    ("俯拍", "high-angle shot"),
    ("仰拍", "low-angle shot"),
)


def _map_movement_en(value: str) -> str:
    v = _clean(value)
    if not v:
        return ""
    lower = v.lower()
    if any(k in lower for k in ("dolly", "pan", "tilt", "orbit", "static", "camera")):
        return v if v[0].isupper() or v.lower().startswith("the ") else f"The camera: {v}"
    for zh, en in _MOVEMENT_EN:
        if zh in v:
            return en
    return f"Camera movement: {v}"


def _map_camera_en(value: str) -> str:
    v = _clean(value)
    if not v:
        return ""
    lower = v.lower()
    if "shot" in lower or "angle" in lower:
        return v
    for zh, en in _CAMERA_EN:
        if zh in v:
            return en
    return _format_camera(v)


def extract_director_fields_from_scene(scene_desc: str) -> tuple[str, str]:
    """从「运镜：…；景别：…」片段提取 movement / camera。"""
    raw = scene_desc or ""
    movement = ""
    camera = ""
    m = _MOVEMENT_LABEL_RE.search(raw)
    if m:
        movement = m.group(1).strip()
    c = _CAMERA_LABEL_RE.search(raw)
    if c:
        camera = c.group(1).strip()
    return movement, camera


def prepend_wan_motion_english(
    scene: str,
    *,
    movement: str = "",
    camera: str = "",
    camera_move: str = "auto",
    shot_scale: str = "auto",
) -> str:
    """将运镜/景别英文句前置到 Wan scene 描述。

    G33：若 camera_move / shot_scale 非 auto，用显式 ID 映射，并跳过文本「运镜：/景别：」解析以免双重注入。
    二者皆 auto 时保持 G31 文本解析路径。
    """
    explicit_move = _map_explicit_camera_move(camera_move)
    explicit_scale = _map_explicit_shot_scale(shot_scale)
    use_explicit = bool(explicit_move or explicit_scale)

    mov = _clean(movement)
    cam = _clean(camera)
    if use_explicit:
        # 显式 UI 优先；不再从 scene 文本抽运镜/景别
        pass
    elif not mov and not cam:
        mov, cam = extract_director_fields_from_scene(scene)

    parts: list[str] = []
    if explicit_move:
        parts.append(explicit_move)
    elif mov:
        parts.append(_map_movement_en(mov))
    if explicit_scale:
        parts.append(explicit_scale)
    elif cam:
        parts.append(_map_camera_en(cam))
    if not parts:
        return scene
    head = ". ".join(parts)
    body = _clean(scene)
    # 去掉中文标签段，避免与英文前置重复堆叠
    if body:
        body = _MOVEMENT_LABEL_RE.sub("", body)
        body = _CAMERA_LABEL_RE.sub("", body)
        body = re.sub(r"[；;]\s*[；;]", "；", body).strip("；; \n")
        body = _clean(body)
    if body:
        return f"{head}. {body}"
    return head


# G33: UI 显式运镜 / 景别 ID → 英文（验收探针断言用词）
_EXPLICIT_CAMERA_MOVE_EN: dict[str, str] = {
    "push_in": "push in",
    "pull_out": "pull out",
    "pan": "pan",
    "track": "tracking shot",
    "static": "static camera",
}
_EXPLICIT_SHOT_SCALE_EN: dict[str, str] = {
    "close": "close-up",
    "medium": "medium shot",
    "wide": "wide shot",
    "full": "full shot",
}


def _normalize_explicit_id(value: str | None) -> str:
    v = (value or "auto").strip().lower()
    return v or "auto"


def _map_explicit_camera_move(camera_move: str | None) -> str:
    key = _normalize_explicit_id(camera_move)
    if key == "auto":
        return ""
    return _EXPLICIT_CAMERA_MOVE_EN.get(key, "")


def _map_explicit_shot_scale(shot_scale: str | None) -> str:
    key = _normalize_explicit_id(shot_scale)
    if key == "auto":
        return ""
    return _EXPLICIT_SHOT_SCALE_EN.get(key, "")


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


@dataclass(frozen=True)
class PromptResult:
    positive_prompt: str
    negative_prompt: str
    model_params: dict


WAN_VIDEO_NEGATIVE = (
    "worst quality, inconsistent motion, blurry, jittery, distorted, "
    "static, text, watermark"
)

WAN_MODEL_PARAMS: dict[str, dict] = {
    "wan-t2v": {"steps": 4, "cfg": 1.0, "width": 848, "height": 480, "fps": 24},
    "wan-i2v": {"steps": 4, "cfg": 1.0, "width": 640, "height": 640, "fps": 24},
}

FLUX_MODEL_PARAMS = {"steps": 20, "cfg": 1.0, "width": 1344, "height": 768}


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
    quality_preset_id: str = "auto",
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

    _, neg_suffix = get_suffixes(quality_preset_id)
    if neg_suffix:
        parts.append(neg_suffix)

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
    quality_preset_id: str = "auto",
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

    preset_id = normalize_quality_preset_id(quality_preset_id)
    pos_suffix, _ = get_suffixes(preset_id)
    if pos_suffix:
        positive = f"{positive}, {pos_suffix}" if positive else pos_suffix

    positive, truncated = _truncate_positive(positive, MAX_POSITIVE_LENGTH[wt])
    negative = _build_negative(
        {}, wt, global_style=style, quality_preset_id=preset_id
    )

    return BuiltPrompt(
        positive=positive,
        negative=negative,
        workflow_type=wt,
        truncated=truncated,
        segments=tuple(gen_parts),
        display_prompt=display,
        parsed_fields={"description": desc, "theme": theme, "style": style},
    )


def summarize_character_refs_for_trace(character_refs: list) -> list[dict]:
    """Compile trace 用：name + appearance 前 50 字摘要。"""
    summary: list[dict] = []
    for item in character_refs or []:
        if not isinstance(item, dict):
            continue
        name = _clean(item.get("name"))
        appearance = _clean(item.get("appearance") or item.get("desc"))
        if not name and not appearance:
            continue
        summary.append({
            "name": name,
            "appearance": appearance[:50] if appearance else "",
        })
    return summary


def _character_ref_lines(character_refs: list) -> list[str]:
    lines: list[str] = []
    for item in character_refs or []:
        if not isinstance(item, dict):
            continue
        name = _clean(item.get("name"))
        appearance = _clean(item.get("appearance") or item.get("desc"))
        if name and appearance:
            lines.append(f"{name}: {appearance}")
        elif name:
            lines.append(name)
        elif appearance:
            lines.append(appearance)
    return lines


def _apply_style_preset(style_preset: str) -> str:
    preset = _clean(style_preset)
    if not preset:
        return ""
    if preset in STYLE_EN_TAGS:
        return STYLE_EN_TAGS[preset]
    return resolve_style_en_tags(preset) or preset


def compress_for_seedance(
    source: str,
    *,
    camera_move: str = "auto",
    shot_scale: str = "auto",
    max_words: int = SEEDANCE_MAX_WORDS,
    min_words: int = SEEDANCE_MIN_WORDS,
) -> PromptResult:
    """
    将长描述压缩为 Seedance 短 prompt（默认 30–100 英文词）。
    运镜/景别短标签前置；去掉 Wan 式长堆砌。
    """
    move = _map_explicit_camera_move(camera_move)
    scale = _map_explicit_shot_scale(shot_scale)
    body = _clean(source)
    # 去掉常见冗余填充
    for noise in (
        "highly detailed",
        "masterpiece",
        "best quality",
        "8k",
        "4k uhd",
        "ultra realistic",
        "intricate details",
    ):
        body = re.sub(re.escape(noise), "", body, flags=re.IGNORECASE)
    body = _clean(body)

    prefix_parts = [p for p in (move, scale) if p]
    prefix = ", ".join(prefix_parts)

    words = body.split()
    # 预留前缀词数
    prefix_n = len(prefix.split()) if prefix else 0
    budget = max(8, int(max_words) - prefix_n)
    if len(words) > budget:
        words = words[:budget]
    body = " ".join(words)

    if prefix and body:
        positive = f"{prefix}. {body}"
    elif prefix:
        positive = prefix
    else:
        positive = body

    # 保证至少 min_words：过短时用中性补全（仍控制在 max_words）
    tokens = positive.split()
    if len(tokens) < min_words:
        filler = (
            "natural lighting clear subject action continuous motion "
            "cinematic framing coherent environment steady pace "
            "visible beat grounded performance clean silhouette "
            "consistent wardrobe practical light soft contrast"
        ).split()
        while len(tokens) < min_words:
            need = min_words - len(tokens)
            tokens.extend(filler[:need])
        positive = " ".join(tokens[:max_words])
    elif len(tokens) > max_words:
        positive = " ".join(tokens[:max_words])

    return PromptResult(
        positive_prompt=positive,
        negative_prompt="",
        model_params=dict(SEEDANCE_MODEL_PARAMS),
    )


def build_prompt(
    scene_desc: str,
    character_refs: list | None = None,
    style_preset: str = "",
    model_target: str = "flux",
    camera_move: str = "auto",
    shot_scale: str = "auto",
) -> PromptResult:
    """
    Prompt Compiler 统一入口。
    优先级：character_refs > scene_desc > style_preset > 模型默认值。
    G33：Wan 路径可接受显式 camera_move / shot_scale（非 auto 时优先于文本解析）。
    """
    target = (model_target or "flux").strip().lower()
    if target not in ("flux", "wan-t2v", "wan-i2v", "seedance"):
        target = "flux"

    scene = _clean(scene_desc)
    char_lines = _character_ref_lines(character_refs or [])
    style_tag = _apply_style_preset(style_preset)

    if target == "seedance":
        parts: list[str] = []
        if char_lines:
            parts.append(", ".join(char_lines))
        if scene:
            parts.append(scene)
        if style_tag and style_tag not in scene:
            parts.append(style_tag)
        long_text = ". ".join(p for p in parts if p)
        return compress_for_seedance(
            long_text,
            camera_move=camera_move,
            shot_scale=shot_scale,
        )

    if target == "flux":
        parts = []
        if char_lines:
            parts.append(", ".join(char_lines))
        if scene:
            parts.append(scene)
        if style_tag and style_tag not in scene:
            parts.append(style_tag)
        positive = ", ".join(p for p in parts if p)
        positive, _ = _truncate_positive(positive, MAX_POSITIVE_LENGTH["flux"])
        return PromptResult(
            positive_prompt=positive,
            negative_prompt="",
            model_params=dict(FLUX_MODEL_PARAMS),
        )

    # Wan：英文优先，运动/运镜描述前置（G31 + G33 显式字段）
    motion = prepend_wan_motion_english(
        scene,
        camera_move=camera_move,
        shot_scale=shot_scale,
    )
    char_en = ", ".join(char_lines)
    wan_parts: list[str] = []
    if motion:
        wan_parts.append(motion)
    if char_en:
        wan_parts.append(char_en)
    if style_tag:
        wan_parts.append(style_tag)
    positive = ". ".join(p for p in wan_parts if p)
    params = dict(WAN_MODEL_PARAMS.get(target, WAN_MODEL_PARAMS["wan-t2v"]))
    return PromptResult(
        positive_prompt=positive,
        negative_prompt=WAN_VIDEO_NEGATIVE,
        model_params=params,
    )
