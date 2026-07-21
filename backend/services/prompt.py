import asyncio
import logging
import re

from core.config import settings
from comfyui import llm
from services.mention_context import strip_mention_tokens
from services.prompt_builder import prompt_has_person_subject

logger = logging.getLogger(__name__)

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


class PromptTranslationError(Exception):
    """生图/生视频 prompt 未能译成英文，禁止提交生成。"""


def contains_cjk(text: str) -> bool:
    return bool(_CHINESE_RE.search(text or ""))


def _cjk_ratio(text: str) -> float:
    s = text or ""
    if not s:
        return 0.0
    return sum(1 for c in s if "\u4e00" <= c <= "\u9fff") / max(len(s), 1)


def _looks_translated(original: str, translated: str) -> bool:
    """译文须明显去中文；允许少量专有名词残留。"""
    cleaned = (translated or "").strip()
    if not cleaned:
        return False
    if cleaned == (original or "").strip():
        return False
    # 原文含中文时，译文 CJK 占比应显著下降
    if _CHINESE_RE.search(original or ""):
        return _cjk_ratio(cleaned) < 0.08 and not (
            _cjk_ratio(cleaned) > 0.02 and _cjk_ratio(cleaned) >= _cjk_ratio(original) * 0.5
        )
    return True


def ensure_generation_prompt_english(positive: str, negative: str = "") -> None:
    """提交 ComfyUI / Seedance 前最终校验：正向/负向均不得含中文。"""
    if contains_cjk(positive):
        raise PromptTranslationError("正向提示词仍含中文，无法提交生成")
    if negative and contains_cjk(negative):
        raise PromptTranslationError("负向提示词仍含中文，无法提交生成")


# 翻译输出：API 无法真正「无限」max_tokens；取常见对话模型可用上限作天花板。
TRANSLATE_MAX_TOKENS = 16384


def _translate_max_tokens(text: str) -> int:
    """不再按原文长度人为压低输出上限。"""
    _ = text
    return TRANSLATE_MAX_TOKENS


def _translate_timeout(text: str) -> float:
    """长文翻译给足时间；仍低于 Cloudflare ~100s 空闲上限。"""
    length = len(text or "")
    # 输出上限抬高后，按输入长度估时，避免短文也干等
    estimated = 20.0 + length / 40.0
    return min(90.0, max(float(settings.optimize_timeout), estimated, 30.0))


async def _l3_fallback_translate(
    text: str,
    *,
    mode: str,
    reason: str,
) -> tuple[str | None, str | None]:
    """L3 翻译，返回 (译文, 失败说明)。"""
    cleaned_in = (text or "").strip()
    if not cleaned_in:
        return None, "空输入"

    logger.warning(
        "[L3_FALLBACK] mode=%s reason=%s input_len=%d",
        mode,
        reason,
        len(cleaned_in),
    )

    notes: list[str] = []
    timeout = _translate_timeout(cleaned_in)
    max_tokens = _translate_max_tokens(cleaned_in)

    try:
        plain = await asyncio.wait_for(
            llm.translate_to_english(
                cleaned_in, mode=mode, max_tokens=max_tokens
            ),
            timeout=timeout,
        )
        if plain.get("error"):
            notes.append(str(plain["error"]))
        else:
            cleaned = (plain.get("positive") or "").strip()
            if cleaned and _looks_translated(cleaned_in, cleaned):
                return cleaned, None
            if cleaned:
                notes.append("译文仍含大量中文或未改变")
            else:
                notes.append("翻译返回空")
    except asyncio.TimeoutError:
        notes.append("翻译超时")
    except Exception as exc:
        notes.append(f"翻译异常: {exc}")

    return None, "；".join(notes) if notes else "翻译未生效"


async def _translate_field_or_raise(
    text: str,
    *,
    mode: str,
    reason: str,
    field_label: str,
) -> str:
    cleaned = (text or "").strip()
    if not cleaned:
        return ""
    if not contains_cjk(cleaned):
        return cleaned
    translated, note = await _l3_fallback_translate(cleaned, mode=mode, reason=reason)
    if not translated:
        detail = note or "翻译未生效"
        raise PromptTranslationError(
            f"{field_label}翻译失败：{detail}。"
            "请在管理后台「模型管理」配置并启用文本 LLM。"
        )
    ensure_generation_prompt_english(translated, "")
    return translated


async def maybe_optimize_prompt(
    prompt: str,
    negative_prompt: str,
    mode: str,
    auto_optimize: bool,
    *,
    model_hint: str | None = None,
) -> tuple[str, str, bool, str | None]:
    """
    返回 (正向, 负向, 是否已优化/翻译, 失败说明)。

    含中文的正向/负向均强制译成英文；翻译失败抛 PromptTranslationError。
    长视频/LTX2 在译成英文后，若 auto_optimize 仍可再压缩（输入已是英文）。
    """
    prompt = strip_mention_tokens(prompt)
    negative_prompt = strip_mention_tokens(negative_prompt or "")
    has_cjk_pos = contains_cjk(prompt)
    has_cjk_neg = contains_cjk(negative_prompt)

    if not has_cjk_pos and not has_cjk_neg:
        ensure_generation_prompt_english(prompt, negative_prompt)
        return prompt, negative_prompt, False, "skipped_no_cjk"

    positive = await _translate_field_or_raise(
        prompt,
        mode=mode,
        reason="cjk_positive_required"
        if auto_optimize
        else "cjk_positive_auto_optimize_disabled",
        field_label="正向提示词",
    )
    negative = await _translate_field_or_raise(
        negative_prompt,
        mode=mode,
        reason="cjk_negative_required",
        field_label="负向提示词",
    )
    optimized = has_cjk_pos or has_cjk_neg

    # LTX2 / 超长视频：译文后再做压缩优化（失败则保留译文）
    hint = (model_hint or "").strip().lower()
    want_compress = (
        auto_optimize
        and mode == "video"
        and (
            hint.startswith("ltx2")
            or hint in {"ltx-2", "ltx2"}
            or len(prompt) >= 800
        )
    )
    if want_compress:
        try:
            result = await asyncio.wait_for(
                llm.optimize_prompt(positive, mode, model_hint=model_hint),
                timeout=settings.optimize_timeout,
            )
            if not result.get("error"):
                compressed = (result.get("positive") or "").strip()
                if compressed and _looks_translated(prompt, compressed):
                    positive = compressed
                    neg2 = (result.get("negative") or "").strip()
                    if neg2:
                        negative = await _translate_field_or_raise(
                            neg2,
                            mode=mode,
                            reason="ltx2_negative_compress",
                            field_label="负向提示词",
                        )
        except PromptTranslationError:
            raise
        except Exception as exc:
            logger.warning("post-translate optimize skipped: %s", exc)

    ensure_generation_prompt_english(positive, negative)
    return positive, negative, optimized, None


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
    """对含人物主体的视频提示追加肢体解剖正向约束。"""
    cleaned = (prompt or "").strip()
    if not cleaned:
        return prompt
    if not prompt_has_person_subject(cleaned):
        return prompt
    suffix = VIDEO_ANATOMY_POSITIVE_SUFFIX
    if suffix.lower() in cleaned.lower():
        return prompt
    merged = f"{cleaned}, {suffix}"
    ensure_generation_prompt_english(merged, "")
    return merged


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
