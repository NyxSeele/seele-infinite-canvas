from comfyui.llm import (
    LTX2_VIDEO_SYSTEM_PROMPT,
    VIDEO_TRANSLATE_PLAIN_SYSTEM,
    WAN_VIDEO_SYSTEM_PROMPT,
    _resolve_optimize_system_prompt,
)


def test_video_translate_plain_system_preserves_character_appearance():
    assert "hairstyle" in VIDEO_TRANSLATE_PLAIN_SYSTEM
    assert "clothing" in VIDEO_TRANSLATE_PLAIN_SYSTEM
    assert "back view" in VIDEO_TRANSLATE_PLAIN_SYSTEM
    assert "fully preserved" in VIDEO_TRANSLATE_PLAIN_SYSTEM


def test_ltx2_optimize_system_prompt_selected():
    prompt = _resolve_optimize_system_prompt("video", "ltx2-fp4")
    assert prompt == LTX2_VIDEO_SYSTEM_PROMPT
    assert "单镜头" in prompt
    assert "人物辨识" in prompt


def test_wan_optimize_system_prompt_selected():
    prompt = _resolve_optimize_system_prompt("video", "wan-2.6")
    assert prompt == WAN_VIDEO_SYSTEM_PROMPT
    assert "Wan" in prompt
