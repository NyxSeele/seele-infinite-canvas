"""SeedVR2 image enhance workflow builder tests."""

from __future__ import annotations

from comfyui.client import build_seedvr2_image_enhance_workflow


def test_seedvr2_image_workflow_nodes():
    wf = build_seedvr2_image_enhance_workflow(
        "test.png",
        upscale_factor=2.0,
        strength="normal",
        model_size="7b",
    )
    types = {n.get("class_type") for n in wf.values()}
    assert "LoadImage" in types
    assert "SeedVR2VideoUpscaler" in types
    assert "SaveImage" in types
    assert "SeedVR2LoadDiTModel" in types
    assert wf["2"]["inputs"]["model"] == "seedvr2_ema_7b_fp16.safetensors"
