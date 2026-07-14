import asyncio
import re

from core.config import settings
from comfyui import llm
from services.mention_context import strip_mention_tokens

_CHINESE_RE = re.compile(r"[\u4e00-\u9fff]")
_WORD_RE = re.compile(r"[a-zA-Z]+")
# 具体主体/动作关键词：命中则视为非抽象短提示
_SPECIFIC_SUBJECT_RE = re.compile(
    r"(人|女|男|孩|猫|狗|鸟|车|花|树|鱼|马|牛|羊|"
    r"走|跑|跳|飞|游|舞|坐|站|躺|骑|开|拿|举|抱|"
    r"woman|man|girl|boy|person|people|cat|dog|bird|car|"
    r"walk|run|jump|dance|sit|stand|drive)",
    re.IGNORECASE,
)

VIDEO_ANATOMY_POSITIVE_SUFFIX = (
    "anatomically correct, proper hand anatomy, five fingers, "
    "natural body proportions"
)


async def _translate_chinese_fallback(
    text: str, *, mode: str = "image"
) -> tuple[str | None, str | None]:
    """L3 优化未生效时的英译回退，返回 (译文, 失败说明)。"""
    if not _CHINESE_RE.search(text or ""):
        return None, None

    notes: list[str] = []

    try:
        plain = await asyncio.wait_for(
            llm.translate_to_english(text, mode=mode),
            timeout=min(settings.optimize_timeout, 20.0),
        )
        if plain.get("error"):
            notes.append(str(plain["error"]))
        else:
            cleaned = (plain.get("positive") or "").strip()
            if cleaned and cleaned != text.strip():
                return cleaned, None
    except asyncio.TimeoutError:
        notes.append("DashScope 翻译超时")
    except Exception as exc:
        notes.append(f"DashScope 翻译异常: {exc}")

    try:
        from providers.comfyui import translate_if_chinese

        translated = await translate_if_chinese(text)
        cleaned = (translated or "").strip()
        if cleaned and cleaned != text.strip():
            return cleaned, None
        notes.append("文本模型未返回有效译文")
    except Exception as exc:
        notes.append(f"文本模型翻译失败: {exc}")

    return None, "；".join(notes) if notes else "翻译未生效"


async def maybe_optimize_prompt(
    prompt: str,
    negative_prompt: str,
    mode: str,
    auto_optimize: bool,
    *,
    model_hint: str | None = None,
) -> tuple[str, str, bool, str | None]:
    """返回 (正向, 负向, 是否已优化, 失败说明)。"""
    prompt = strip_mention_tokens(prompt)
    translate_note: str | None = None

    if auto_optimize and mode == "image" and _CHINESE_RE.search(prompt):
        translated, note = await _translate_chinese_fallback(prompt, mode="image")
        if translated:
            prompt = translated
        else:
            translate_note = note

    if auto_optimize and mode == "video" and _CHINESE_RE.search(prompt):
        translated, note = await _translate_chinese_fallback(prompt, mode="video")
        if translated:
            prompt = translated
        else:
            translate_note = note

    if not auto_optimize:
        translated, note = await _translate_chinese_fallback(prompt, mode=mode)
        if translated:
            return translated, negative_prompt, True, None
        return prompt, negative_prompt, False, note

    positive = prompt
    negative = negative_prompt
    optimized = False

    try:
        result = await asyncio.wait_for(
            llm.optimize_prompt(prompt, mode, model_hint=model_hint),
            timeout=settings.optimize_timeout,
        )
        if result.get("error"):
            translate_note = str(result["error"])
        else:
            positive = result["positive"]
            negative = result.get("negative") or negative_prompt
            optimized = positive.strip() != prompt.strip()
    except asyncio.TimeoutError:
        translate_note = "提示词优化超时"
    except Exception as exc:
        translate_note = f"提示词优化异常: {exc}"

    if not optimized and _CHINESE_RE.search(positive):
        translated, note = await _translate_chinese_fallback(positive, mode=mode)
        if translated:
            positive = translated
            optimized = True
            translate_note = None
        elif note:
            translate_note = note

    return positive, negative, optimized, translate_note


def is_short_abstract_video_prompt(text: str) -> bool:
    """极短/抽象视频提示：英文词数≤4，或中文≤8字且无具体主体/动作。"""
    cleaned = strip_mention_tokens(text or "").strip()
    if not cleaned:
        return False
    if _CHINESE_RE.search(cleaned):
        if len(cleaned) > 8:
            return False
        return _SPECIFIC_SUBJECT_RE.search(cleaned) is None
    words = _WORD_RE.findall(cleaned)
    return len(words) <= 4


def apply_video_anatomy_guard(prompt: str) -> str:
    """对所有视频提示追加肢体解剖正向约束。"""
    cleaned = (prompt or "").strip()
    if not cleaned:
        return prompt
    suffix = VIDEO_ANATOMY_POSITIVE_SUFFIX
    if suffix.lower() in cleaned.lower():
        return prompt
    return f"{cleaned}, {suffix}"


def is_high_risk_freeref_i2v(
    *,
    generation_mode: str | None,
    workflow_mode: str,
    has_reference_image: bool,
    prompt: str,
) -> bool:
    """freeref + 参考图 I2V + 极短抽象提示 → 肢体幻觉高风险。"""
    if workflow_mode != "image2video" or not has_reference_image:
        return False
    if (generation_mode or "").strip().lower() != "freeref":
        return False
    return is_short_abstract_video_prompt(prompt)


def resolve_video_sampling_profile(
    *,
    sampling_profile: str | None,
    generation_mode: str | None,
    workflow_mode: str,
    has_reference_image: bool,
    prompt: str,
    video_backend: str,
) -> tuple[str, str | None]:
    """高风险 Wan freeref I2V 自动从 fast 升档到 quality。返回 (profile, reason)。"""
    profile = (sampling_profile or "fast").strip().lower()
    if profile not in ("fast", "quality"):
        profile = "fast"
    if profile == "quality":
        return "quality", None
    if video_backend != "wan":
        return profile, None
    if is_high_risk_freeref_i2v(
        generation_mode=generation_mode,
        workflow_mode=workflow_mode,
        has_reference_image=has_reference_image,
        prompt=prompt,
    ):
        return "quality", "freeref_i2v_short_abstract_prompt"
    return profile, None
