import pytest

from services.prompt_builder import ANIME_NEGATIVE_EN, build_script_shot_prompt
from services.script_shot_strategy import (
    DENOISE_IMG2IMG_CONTINUITY,
    detect_new_subject,
    evaluate_visual_reference,
    new_subject_emphasis,
)


def test_detect_new_subject_cat():
    assert detect_new_subject(
        "回头看见一只小猫",
        "雨夜街道，少女回头",
    )


def test_detect_new_subject_same_scene():
    assert not detect_new_subject(
        "少女继续在雨中奔跑",
        "雨夜街道，少女回头",
    )


def test_evaluate_new_subject_uses_txt2img():
    decision = evaluate_visual_reference(
        description="回头看见一只猫",
        prior_description="少女在雨夜中行走",
        visual_continuity=True,
        shot_number=2,
        has_manual_reference=False,
        has_previous_shot_image=True,
    )
    assert decision.use_visual_reference is False
    assert decision.img2img_denoise is None
    assert decision.visual_mode == "new_subject"
    assert decision.note


def test_new_subject_emphasis_cat():
    text = new_subject_emphasis("回头看见一只猫")
    assert "猫" in text


def test_evaluate_continuity_denoise():
    decision = evaluate_visual_reference(
        description="少女继续在雨中奔跑",
        prior_description="雨夜街道，少女回头",
        visual_continuity=True,
        shot_number=2,
        has_manual_reference=False,
        has_previous_shot_image=True,
    )
    assert decision.use_visual_reference is True
    assert decision.img2img_denoise == DENOISE_IMG2IMG_CONTINUITY


def test_evaluate_shot_one_no_ref():
    decision = evaluate_visual_reference(
        description="开场",
        prior_description=None,
        visual_continuity=True,
        shot_number=1,
        has_manual_reference=False,
        has_previous_shot_image=False,
    )
    assert decision.use_visual_reference is False


def test_anime_negative_on_script_shot():
    built = build_script_shot_prompt(
        "少女回头",
        "sd15",
        global_style="二次元",
    )
    assert ANIME_NEGATIVE_EN.split(",")[0].strip() in built.negative
