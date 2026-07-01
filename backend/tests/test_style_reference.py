import pytest

from services.prompt_builder import build_script_shot_prompt
from services.shot_prompt_package import _rule_package
from services.style_reference_service import format_style_for_prompt, parse_style_reference


SAMPLE_REF = {
    "color_tone": "desaturated cold gray",
    "lighting": "side backlight",
    "shot_language": "close-ups and shallow depth of field",
    "atmosphere": "tense suspense",
    "style_keywords": ["noir", "cinematic", "desaturated"],
    "source": "user_upload",
    "extracted_at": "2026-06-30T10:00:00Z",
}


def test_format_style_for_prompt():
    text = format_style_for_prompt(SAMPLE_REF)
    assert "[风格参考：" in text
    assert "desaturated cold gray" in text
    assert "noir" in text


def test_format_style_for_prompt_empty():
    assert format_style_for_prompt(None) == ""
    assert format_style_for_prompt({}) == ""


def test_parse_style_reference():
    raw = '{"color_tone": "warm", "style_keywords": ["golden hour"]}'
    data = parse_style_reference(raw)
    assert data["color_tone"] == "warm"
    assert data["style_keywords"] == ["golden hour"]


def test_build_script_shot_injects_style_reference():
    built = build_script_shot_prompt(
        "少女在雨中回头",
        "sd15",
        style_reference=SAMPLE_REF,
    )
    assert "风格参考" in built.positive
    assert "noir" in built.positive


def test_rule_package_injects_style_reference():
    payload = {
        "row": {"prompt": "test shot", "duration": 8, "shot_number": 1},
        "cast_library": [],
        "style_reference": SAMPLE_REF,
    }
    result = _rule_package(payload)
    assert "风格参考" in result["atmosphere"]
    assert "noir" in result["atmosphere"]
