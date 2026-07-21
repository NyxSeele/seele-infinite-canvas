"""Model catalog metadata exposed via /api/models."""

from model_registry import get_model_catalog_meta


def test_qwen_image_recommended():
    meta = get_model_catalog_meta("qwen-image")
    assert meta["recommended"] is True
    assert "文字" in meta["summary"]
    assert meta["sort_rank"] == 10


def test_ltx2_fp4_recommended_modes():
    meta = get_model_catalog_meta("ltx2-fp4")
    assert meta["recommended_modes"][0] == "i2v"
    assert "t2v" in meta["recommended_modes"]
    assert meta["sort_rank"] == 40


def test_wan_26_recommended_for_t2v():
    meta = get_model_catalog_meta("wan-2.6")
    assert meta.get("recommended") is True
    assert meta["sort_rank"] == 10
    assert "文字" in meta["summary"]


def test_wan_i2v_keyframe_recommendation():
    meta = get_model_catalog_meta("wan-i2v")
    assert meta["recommended_modes"] == ["keyframe"]
    assert meta.get("recommended") is True
    assert "首尾" in meta["summary"]
