"""SeedVR2 enhance defaults / model selection."""

from __future__ import annotations

from comfyui.client import (
    SEEDVR2_DIT_3B,
    SEEDVR2_DIT_NORMAL,
    SEEDVR2_DIT_SHARP,
    _seedvr2_dit_model,
    build_seedvr2_enhance_workflow,
    build_seedvr2_image_enhance_workflow,
)
from services.gpu_pool import GPUNode, GPUPool, parse_comfyui_node_spec
from services.video_enhance_recommend import normalize_enhance_params, _rule_recommend_params


def test_seedvr2_default_is_7b_fp16():
    assert _seedvr2_dit_model("normal") == SEEDVR2_DIT_NORMAL
    assert _seedvr2_dit_model("sharp") == SEEDVR2_DIT_SHARP
    assert _seedvr2_dit_model("normal", "3b") == SEEDVR2_DIT_3B


def test_seedvr2_video_workflow_defaults_7b():
    wf = build_seedvr2_enhance_workflow("clip.mp4")
    assert wf["2"]["inputs"]["model"] == SEEDVR2_DIT_NORMAL


def test_seedvr2_image_workflow_defaults_7b():
    wf = build_seedvr2_image_enhance_workflow("test.png")
    assert wf["2"]["inputs"]["model"] == SEEDVR2_DIT_NORMAL


def test_normalize_and_rule_default_7b(monkeypatch):
    monkeypatch.setattr(
        "services.video_enhance_recommend.default_seedvr_model_size",
        lambda: "7b",
    )
    assert normalize_enhance_params({})["model_size"] == "7b"
    params, _ = _rule_recommend_params({"width": 1280, "height": 720, "duration": 5.0})
    assert params["model_size"] == "7b"
    assert params["strength"] == "normal"


def test_parse_node_vram_spec():
    url, vram, caps = parse_comfyui_node_spec(
        "https://u1066791-90fc-c93a7df9.westb.seetacloud.com:8443|80"
    )
    assert url.endswith(":8443")
    assert vram == 80
    assert "video" in caps
    assert parse_comfyui_node_spec("http://127.0.0.1:8000")[1] == 32


def test_seedvr2_enhance_routes_to_h800():
    pool = GPUPool(
        nodes=[
            GPUNode("gpu-0", "http://127.0.0.1:8000", 32),
            GPUNode("gpu-1", "https://h800.example:8443", 80),
        ]
    )
    node = pool.get_available_node(required_vram=40)
    assert node.comfyui_url.endswith(":8443")
    assert node.available_vram == 80
