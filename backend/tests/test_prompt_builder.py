import pytest

from services.prompt_builder import (
    DEFAULT_NEGATIVE_ZH,
    FLUX_QUALITY_SUFFIX,
    apply_flux_positive_suffixes,
    build_hunyuan_prompt,
    build_prompt,
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


def test_script_shot_cinematic_preset_suffix():
    built = build_script_shot_prompt(
        "雨夜街道，少女回头",
        "sd15",
        quality_preset_id="cinematic",
    )
    assert "photorealistic" in built.positive
    assert "35mm film" in built.positive
    assert "anime" in built.negative
    assert "cartoon" in built.negative


def test_script_shot_auto_preset_no_suffix():
    built = build_script_shot_prompt(
        "雨夜街道，少女回头",
        "sd15",
        quality_preset_id="auto",
    )
    assert "35mm film" not in built.positive
    assert "anime" not in built.negative or "模糊" in built.negative


def test_script_shot_documentary_preset_suffix():
    built = build_script_shot_prompt(
        "街头采访",
        "sd15",
        quality_preset_id="documentary",
    )
    assert "documentary photography" in built.positive
    assert "anime" in built.negative


def test_script_shot_dark_drama_preset_suffix():
    built = build_script_shot_prompt(
        "暗室对峙",
        "sd15",
        quality_preset_id="dark_drama",
    )
    assert "low key lighting" in built.positive


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


def test_compile_prompt_flux_priority():
    result = build_prompt(
        "sunset over mountains",
        character_refs=[{"name": "Alice", "appearance": "silver hair"}],
        style_preset="电影感",
        model_target="flux",
    )
    assert "Alice" in result.positive_prompt
    assert "sunset" in result.positive_prompt
    assert "sharp focus" in result.positive_prompt
    assert result.negative_prompt == ""
    assert result.model_params.get("width") == 1344


def test_apply_flux_positive_suffixes_person():
    out = apply_flux_positive_suffixes("a woman in the rain")
    assert "sharp focus" in out
    assert "proper hand anatomy" in out


def test_build_hunyuan_prompt_person():
    out = build_hunyuan_prompt("a girl walking in rain")
    assert "cinematic quality" in out
    assert "proper hand anatomy" in out


def test_build_hunyuan_prompt_landscape():
    out = build_hunyuan_prompt("mountain sunrise")
    assert "cinematic quality" in out
    assert "proper hand anatomy" not in out


def test_compile_prompt_wan_i2v():
    result = build_prompt(
        "camera slowly pans left, girl turns her head",
        character_refs=[{"name": "Mia", "appearance": "red dress"}],
        style_preset="cinematic",
        model_target="wan-i2v",
    )
    assert "camera slowly" in result.positive_prompt
    assert result.negative_prompt
    assert result.model_params.get("steps") == 4
    assert result.model_params.get("width") == 640


def test_g31_wan_prepend_movement_from_labels():
    from services.prompt_builder import prepend_wan_motion_english

    out = prepend_wan_motion_english(
        "雨中街道，女子撑伞；运镜：缓慢推近；景别：中景"
    )
    assert "dollies in" in out.lower()
    assert "medium shot" in out.lower()
    assert "运镜" not in out


def test_g31_build_prompt_wan_injects_dolly():
    result = build_prompt(
        "女子撑伞走入雨中；运镜：缓慢推近；景别：中景",
        model_target="wan-i2v",
    )
    low = result.positive_prompt.lower()
    assert "dollies in" in low or "dolly" in low
    assert "medium shot" in low


def test_g33_explicit_push_in():
    result = build_prompt(
        "rainy street, woman with umbrella",
        model_target="wan-i2v",
        camera_move="push_in",
        shot_scale="auto",
    )
    assert "push in" in result.positive_prompt.lower()


def test_g33_explicit_auto_no_motion_words():
    result = build_prompt(
        "rainy street, woman with umbrella",
        model_target="wan-i2v",
        camera_move="auto",
        shot_scale="auto",
    )
    low = result.positive_prompt.lower()
    for banned in ("push in", "pull out", "tracking shot", "static camera", "medium shot", "close-up", "wide shot", "full shot"):
        assert banned not in low


def test_g33_explicit_medium_shot():
    result = build_prompt(
        "rainy street, woman with umbrella",
        model_target="wan-i2v",
        camera_move="auto",
        shot_scale="medium",
    )
    assert "medium shot" in result.positive_prompt.lower()


def test_g33_explicit_overrides_text_labels():
    """显式非 auto 时跳过文本运镜解析，避免双重注入。"""
    result = build_prompt(
        "女子撑伞；运镜：缓慢推近；景别：中景",
        model_target="wan-i2v",
        camera_move="pan",
        shot_scale="close",
    )
    low = result.positive_prompt.lower()
    assert "pan" in low
    assert "close-up" in low
    assert "dollies in" not in low
    assert "medium shot" not in low
