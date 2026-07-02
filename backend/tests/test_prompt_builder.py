import pytest

from services.prompt_builder import (
    DEFAULT_NEGATIVE_ZH,
    build_prompt_from_fields,
    build_script_shot_prompt,
    infer_fields_from_description_rule,
    normalize_workflow_type,
    resolve_style_en_tags,
)


def test_flux_no_negative():
    built = build_prompt_from_fields(
        {"description": "a cat on the roof", "unwanted": "blur"},
        "flux",
    )
    assert built.negative == ""
    assert built.workflow_type == "flux"
    assert "cat" in built.positive


def test_sd_includes_negative():
    built = build_prompt_from_fields(
        {"description": "sunset beach"},
        "sd15",
    )
    assert built.negative == DEFAULT_NEGATIVE_ZH
    assert "sunset beach" in built.positive


def test_script_shot_clean_display():
    built = build_script_shot_prompt(
        "雨夜街道，少女回头",
        "sd15",
        global_style="二次元",
        theme_context="雨夜街道，同一少女",
    )
    assert built.display_prompt == "雨夜街道，少女回头"
    assert "same story" not in built.positive
    assert "anime style" in built.positive
    assert "雨夜街道，同一少女" in built.positive


def test_script_shot_continuity_respects_mode_off():
    built = build_script_shot_prompt(
        "回头看见一只小猫",
        "sd15",
        prior_shots=[{"shot_number": 1, "description": "雨夜街道，少女回头"}],
        shot_number=2,
        continuity_mode=False,
    )
    assert "承接上一镜头" not in built.positive


def test_script_shot_new_subject_emphasis():
    built = build_script_shot_prompt(
        "回头看见一只猫",
        "sd15",
        theme_context="少女在雨夜中行走",
        prior_shots=[{"shot_number": 1, "description": "少女在雨夜中行走"}],
        shot_number=2,
    )
    assert "猫" in built.positive
    assert "清晰" in built.positive or "焦点" in built.positive


def test_script_shot_continuity_chinese():
    built = build_script_shot_prompt(
        "回头看见一只小猫",
        "sd15",
        global_style="二次元",
        theme_context="雨夜街道，同一少女主角",
        prior_shots=[{"shot_number": 1, "description": "雨夜街道，少女回头"}],
        shot_number=2,
    )
    assert built.display_prompt == "回头看见一只小猫"
    assert "承接上一镜头" in built.positive
    assert "小猫" in built.positive
    assert "same story" not in built.positive


def test_script_shot_photorealistic_cinema_content_style():
    built = build_script_shot_prompt(
        "雨夜街道，少女回头",
        "sd15",
        content_style="photorealistic_cinema",
    )
    assert "photorealistic" in built.positive
    assert "35mm film" in built.positive
    assert "anime" in built.negative
    assert "cartoon" in built.negative


def test_script_shot_generic_content_style_unchanged():
    built = build_script_shot_prompt(
        "雨夜街道，少女回头",
        "sd15",
        content_style="generic",
    )
    assert "35mm film" not in built.positive
    assert "anime" not in built.negative or "模糊" in built.negative


def test_script_shot_style_reference():
    ref = {
        "color_tone": "muted teal",
        "lighting": "soft rim light",
        "shot_language": "wide establishing shots",
        "style_keywords": ["cinematic"],
    }
    built = build_script_shot_prompt(
        "海边日落",
        "flux",
        style_reference=ref,
    )
    assert "风格参考" in built.positive
    assert "cinematic" in built.positive


def test_style_en_tags():
    assert "anime" in resolve_style_en_tags("二次元")


def test_rule_parse_camera():
    fields = infer_fields_from_description_rule("全景，雨夜街道")
    assert fields.get("camera") == "全景"
    assert "雨夜" in fields.get("description", "")


@pytest.mark.parametrize(
    "raw,expected",
    [
        ("flux", "flux"),
        ("SDXL", "sdxl"),
        ("unknown", "sd15"),
        (None, "sd15"),
    ],
)
def test_normalize_workflow_type(raw, expected):
    assert normalize_workflow_type(raw) == expected


def test_rule_package_ignores_segment_context():
    from services.shot_prompt_package import _rule_package

    marker = "__SEGMENT_PROBE_SECRET__"
    pkg = _rule_package(
        {
            "row": {
                "shot_number": 1,
                "duration": 8,
                "description": "雨夜街道，少女回头",
                "prompt": "雨夜街道，少女回头",
            },
            "cast_library": [],
            "scene_library": [],
            "segments": [
                {
                    "title": "夜晚",
                    "description": marker,
                    "duration": 5,
                }
            ],
        }
    )
    full_text = (pkg.get("full_text") or "") + (pkg.get("frames") or "")
    assert marker not in full_text
