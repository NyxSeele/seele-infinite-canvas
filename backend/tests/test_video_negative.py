from comfyui.client import DEFAULT_VIDEO_NEGATIVE, normalize_video_negative
from services.prompt import (
    VIDEO_ANATOMY_POSITIVE_SUFFIX,
    apply_video_anatomy_guard,
    is_high_risk_freeref_i2v,
    is_short_abstract_video_prompt,
    resolve_video_sampling_profile,
)
from services.prompt_builder import WAN_VIDEO_NEGATIVE, merge_wan_negative


def test_default_video_negative_includes_anatomy_terms():
    for term in ("bad anatomy", "extra hands", "extra fingers", "deformed hands"):
        assert term in DEFAULT_VIDEO_NEGATIVE
        assert term in WAN_VIDEO_NEGATIVE
    for term in ("missing fingers", "fused fingers", "mutated hands", "malformed limbs"):
        assert term in WAN_VIDEO_NEGATIVE


def test_normalize_video_negative_merges_user_and_default():
    merged = normalize_video_negative("custom artifact")
    assert "custom artifact" in merged
    assert "extra hands" in merged
    assert "bad anatomy" in merged


def test_normalize_video_negative_empty_uses_default():
    assert normalize_video_negative("") == DEFAULT_VIDEO_NEGATIVE


def test_merge_wan_negative():
    wan = merge_wan_negative("custom")
    assert "custom" in wan
    assert "fused fingers" in wan


def test_short_abstract_video_prompt_detection():
    assert is_short_abstract_video_prompt("超绝动态效果")
    assert is_short_abstract_video_prompt("Ultra-dynamic effect.")
    assert not is_short_abstract_video_prompt(
        "A woman walks through neon streets at night with rain"
    )
    assert not is_short_abstract_video_prompt("一个女人在雨中走路")


def test_apply_video_anatomy_guard_skips_non_person_prompt():
    result = apply_video_anatomy_guard("Ultra-dynamic effect.")
    assert result == "Ultra-dynamic effect."
    assert VIDEO_ANATOMY_POSITIVE_SUFFIX not in result


def test_apply_video_anatomy_guard_appends_for_short_person_prompt():
    result = apply_video_anatomy_guard("A woman in motion.")
    assert "A woman in motion." in result
    assert VIDEO_ANATOMY_POSITIVE_SUFFIX in result


def test_apply_video_anatomy_guard_appends_for_long_prompt():
    long_prompt = (
        "A woman walks through neon streets at night with rain reflections"
    )
    result = apply_video_anatomy_guard(long_prompt)
    assert long_prompt in result
    assert VIDEO_ANATOMY_POSITIVE_SUFFIX in result


def test_apply_video_anatomy_guard_idempotent():
    once = apply_video_anatomy_guard("a woman dancing")
    twice = apply_video_anatomy_guard(once)
    assert once == twice
    assert VIDEO_ANATOMY_POSITIVE_SUFFIX in once


def test_high_risk_freeref_i2v_detection():
    assert is_high_risk_freeref_i2v(
        generation_mode="freeref",
        workflow_mode="image2video",
        has_reference_image=True,
        prompt="超绝动态效果",
    )
    assert not is_high_risk_freeref_i2v(
        generation_mode="keyframe",
        workflow_mode="image2video",
        has_reference_image=True,
        prompt="超绝动态效果",
    )
    assert not is_high_risk_freeref_i2v(
        generation_mode="freeref",
        workflow_mode="text2video",
        has_reference_image=False,
        prompt="超绝动态效果",
    )


def test_resolve_video_sampling_profile_upgrades_high_risk():
    profile, reason = resolve_video_sampling_profile(
        sampling_profile="fast",
        generation_mode="freeref",
        workflow_mode="image2video",
        has_reference_image=True,
        prompt="超绝动态效果",
        video_backend="wan",
    )
    assert profile == "quality"
    assert reason == "freeref_i2v_short_abstract_prompt"


def test_resolve_video_sampling_profile_keeps_explicit_quality():
    profile, reason = resolve_video_sampling_profile(
        sampling_profile="quality",
        generation_mode="freeref",
        workflow_mode="image2video",
        has_reference_image=True,
        prompt="超绝动态效果",
        video_backend="wan",
    )
    assert profile == "quality"
    assert reason is None


def test_resolve_video_sampling_profile_keeps_fast_for_detailed_person_i2v():
    profile, reason = resolve_video_sampling_profile(
        sampling_profile="fast",
        generation_mode="freeref",
        workflow_mode="image2video",
        has_reference_image=True,
        prompt="A woman walks through neon streets at night with rain reflections",
        video_backend="wan",
    )
    assert profile == "fast"
    assert reason is None


def test_resolve_wan_default_fast_when_unset():
    profile, reason = resolve_video_sampling_profile(
        sampling_profile=None,
        generation_mode="t2v",
        workflow_mode="text2video",
        has_reference_image=False,
        prompt="a cat walks",
        video_backend="wan",
    )
    assert profile == "fast"
    assert reason is None
