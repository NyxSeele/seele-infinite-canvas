"""分镜表视觉连贯策略：何时 img2img、denoise 取值（纯文本启发式，不依赖 GPU）。"""

from __future__ import annotations

import re
from dataclasses import dataclass

# 连贯参考上一镜成片时提高 denoise，减轻画面被锁死
DENOISE_IMG2IMG_CONTINUITY = 0.7
# 新主体场景若仍 img2img，需极高 denoise（多数模型仍难「加」出猫，故默认改 txt2img）
DENOISE_IMG2IMG_NEW_SUBJECT = 0.95
DENOISE_IMG2IMG_MANUAL_REF = 0.55

_NEW_ENTITY_MARKERS = (
    "出现",
    "出现了",
    "看见",
    "看见了",
    "发现",
    "发现了",
    "跑来",
    "跑来一只",
    "飞来",
    "跳出来",
    "旁边有",
    "多了",
)

_QUANTIFIER_ENTITY_RE = re.compile(
    r"(?:一只|一个|一位|一条|一辆|一匹|一头)([\u4e00-\u9fff]{1,8})"
)


@dataclass(frozen=True)
class VisualReferenceDecision:
    use_visual_reference: bool
    img2img_denoise: float | None
    visual_mode: str = "none"
    note: str | None = None


def _normalize_desc(text: str | None) -> str:
    if not text:
        return ""
    return " ".join(str(text).strip().split())


def detect_new_subject(current_desc: str, prior_desc: str) -> bool:
    """
    相对上一镜描述，当前镜是否引入明显新主体。
    用于在「视觉参考上一镜」开启时决定是否降级 txt2img。
    """
    current = _normalize_desc(current_desc)
    prior = _normalize_desc(prior_desc)
    if not current or not prior:
        return False

    for marker in _NEW_ENTITY_MARKERS:
        if marker in current and marker not in prior:
            return True

    for match in _QUANTIFIER_ENTITY_RE.finditer(current):
        entity = match.group(1)
        if entity and entity not in prior:
            return True

    return False


def new_subject_emphasis(description: str) -> str:
    """为 generation prompt 增加新主体可见性强调（中文，供 L3 翻译）。"""
    current = _normalize_desc(description)
    if not current:
        return ""
    for match in _QUANTIFIER_ENTITY_RE.finditer(current):
        phrase = match.group(0)
        return f"画面须清晰呈现{phrase}，{phrase}为视觉焦点"
    if "猫" in current or "小猫" in current:
        return "画面须清晰呈现一只猫，猫为视觉焦点"
    return "本镜头新增的人或物须清晰可见"


def evaluate_visual_reference(
    *,
    description: str,
    prior_description: str | None,
    visual_continuity: bool,
    shot_number: int,
    has_manual_reference: bool,
    has_previous_shot_image: bool,
) -> VisualReferenceDecision:
    """
    决定是否使用上一镜成片作 img2img，以及 denoise。
    镜号 1 或用户未开视觉连贯：不自动参考上一镜成片。
    """
    if has_manual_reference:
        return VisualReferenceDecision(
            use_visual_reference=True,
            img2img_denoise=DENOISE_IMG2IMG_MANUAL_REF,
            visual_mode="manual",
            note=None,
        )

    if not visual_continuity or shot_number <= 1:
        return VisualReferenceDecision(
            False,
            None,
            visual_mode="none",
            note=None,
        )

    if not has_previous_shot_image:
        return VisualReferenceDecision(
            False,
            None,
            visual_mode="no_prior_image",
            note="上一镜尚无成片，本镜使用文生图",
        )

    prior = _normalize_desc(prior_description)
    if detect_new_subject(description, prior):
        # img2img 强锁上一镜构图/色调，SD1.5 很难在 0.7–0.8 加出「猫」等新实体；
        # 剧情连贯靠 prompt 注入，视觉靠 txt2img 更易出猫。
        return VisualReferenceDecision(
            False,
            None,
            visual_mode="new_subject",
            note="检测到新主体：已改用文生图并强化 prompt（剧情仍承接上一镜）",
        )

    return VisualReferenceDecision(
        True,
        DENOISE_IMG2IMG_CONTINUITY,
        visual_mode="continuity",
        note="使用上一镜成片参考（连贯视觉）",
    )
