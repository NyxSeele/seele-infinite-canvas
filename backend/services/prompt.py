import asyncio
import re

from core.config import settings
from comfyui import llm
from services.mention_context import strip_mention_tokens

_CHINESE_RE = re.compile(r"[\u4e00-\u9fff]")


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
) -> tuple[str, str, bool, str | None]:
    """返回 (正向, 负向, 是否已优化, 失败说明)。"""
    prompt = strip_mention_tokens(prompt)
    translate_note: str | None = None

    if auto_optimize and mode == "image" and _CHINESE_RE.search(prompt):
        translated, note = await _translate_chinese_fallback(prompt, mode="image")
        if translated:
            return translated, negative_prompt, True, None
        translate_note = note

    if auto_optimize and mode == "video" and _CHINESE_RE.search(prompt):
        translated, note = await _translate_chinese_fallback(prompt, mode="video")
        if translated:
            return translated, negative_prompt, True, None
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
            llm.optimize_prompt(prompt, mode),
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
