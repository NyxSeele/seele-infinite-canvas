"""Prompt translation / compile path."""

from __future__ import annotations

import asyncio

import pytest

from services.prompt import (
    PromptTranslationError,
    _looks_translated,
    maybe_optimize_prompt,
)


def test_chinese_prompt_must_translate(monkeypatch):
    async def _fake_translate(text, *, mode="image", max_tokens=None):
        return {"positive": "An orange cat on the windowsill", "error": None}

    monkeypatch.setattr("comfyui.llm.translate_to_english", _fake_translate)

    positive, negative, optimized, note = asyncio.run(
        maybe_optimize_prompt(
            "一只橘猫坐在窗台上",
            "",
            "image",
            True,
            model_hint="hidream",
        )
    )
    assert optimized is True
    assert note is None
    assert positive == "An orange cat on the windowsill"
    assert "橘" not in positive


def test_chinese_negative_must_translate(monkeypatch):
    async def _fake_translate(text, *, mode="image", max_tokens=None):
        if "模糊" in text:
            return {"positive": "blurry, low quality, watermark, text", "error": None}
        return {"positive": "A rainy street at night", "error": None}

    monkeypatch.setattr("comfyui.llm.translate_to_english", _fake_translate)

    positive, negative, optimized, note = asyncio.run(
        maybe_optimize_prompt(
            "雨夜街道",
            "模糊, 低质量, 水印",
            "image",
            True,
        )
    )
    assert optimized is True
    assert note is None
    assert "雨" not in positive
    assert "模糊" not in negative
    assert "blurry" in negative


def test_translation_failure_raises(monkeypatch):
    async def _fake_translate(text, *, mode="image", max_tokens=None):
        return {"positive": text, "error": "翻译失败"}

    monkeypatch.setattr("comfyui.llm.translate_to_english", _fake_translate)

    with pytest.raises(PromptTranslationError):
        asyncio.run(
            maybe_optimize_prompt(
                "一只橘猫坐在窗台上",
                "",
                "image",
                True,
            )
        )


def test_looks_translated_rejects_unchanged_chinese():
    src = "高中放学时刻，夕阳透过窗户洒进来"
    assert not _looks_translated(src, src)
    assert _looks_translated(
        src, "After school at high school, sunset light streams through windows"
    )
