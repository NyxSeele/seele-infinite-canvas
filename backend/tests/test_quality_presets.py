"""画风预设与画质增强 profile 测试。"""

import pytest

from services.quality_presets import (
    is_cinematic_enhance_preset,
    migrate_content_style_to_preset,
    normalize_quality_preset_id,
)
from services.video_enhance_recommend import _apply_cinematic_param_overrides, _rule_recommend_params


def test_migrate_content_style_photorealistic_to_cinematic():
    assert migrate_content_style_to_preset("photorealistic_cinema", "auto") == "cinematic"
    assert migrate_content_style_to_preset(None, "auto") == "cinematic"


def test_migrate_content_style_generic_stays_auto():
    assert migrate_content_style_to_preset("generic", "auto") == "auto"


def test_migrate_preserves_explicit_default():
    assert migrate_content_style_to_preset("photorealistic_cinema", "documentary") == "documentary"


def test_cinematic_enhance_presets():
    assert is_cinematic_enhance_preset("cinematic") is True
    assert is_cinematic_enhance_preset("documentary") is True
    assert is_cinematic_enhance_preset("dark_drama") is True
    assert is_cinematic_enhance_preset("commercial") is False
    assert is_cinematic_enhance_preset("auto") is False


def test_unknown_preset_normalizes_to_auto():
    assert normalize_quality_preset_id("unknown") == "auto"


def test_cinematic_preset_enhance_noise_override():
    params, _ = _rule_recommend_params(
        {"width": 1280, "height": 720, "duration": 5.0},
        quality_preset_id="cinematic",
    )
    out = _apply_cinematic_param_overrides(
        params,
        {"width": 1280, "height": 720},
        quality_preset_id="cinematic",
    )
    assert out["input_noise_scale"] == pytest.approx(0.15)
    assert out["upscale_factor"] == 2.0


def test_auto_preset_enhance_no_cinematic_override():
    params, _ = _rule_recommend_params(
        {"width": 1280, "height": 720, "duration": 5.0},
        quality_preset_id="auto",
    )
    out = _apply_cinematic_param_overrides(
        params,
        {"width": 1280, "height": 720},
        quality_preset_id="auto",
    )
    assert out["input_noise_scale"] == 0.25
