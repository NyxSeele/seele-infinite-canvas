from comfyui.llm import VIDEO_TRANSLATE_PLAIN_SYSTEM


def test_video_translate_plain_system_preserves_character_appearance():
    assert "hairstyle" in VIDEO_TRANSLATE_PLAIN_SYSTEM
    assert "clothing" in VIDEO_TRANSLATE_PLAIN_SYSTEM
    assert "back view" in VIDEO_TRANSLATE_PLAIN_SYSTEM
    assert "fully preserved" in VIDEO_TRANSLATE_PLAIN_SYSTEM
