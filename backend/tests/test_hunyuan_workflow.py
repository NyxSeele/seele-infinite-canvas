"""HunyuanVideo workflow unit tests (no GPU)."""

from __future__ import annotations

from comfyui.client import (
    HUNYUAN15_CFG_DEFAULT,
    HUNYUAN15_CFG_DISTILLED,
    HUNYUAN15_CKPT,
    HUNYUAN15_DISTILLED_STEPS,
    HUNYUAN_CKPT,
    HUNYUAN_DEFAULT_HEIGHT,
    HUNYUAN_DEFAULT_STEPS,
    HUNYUAN_DEFAULT_WIDTH,
    build_hunyuan_video_workflow,
)
from model_registry import MODEL_MAP, resolve_video_backend


def test_hunyuan_registry_aligned():
    entry = MODEL_MAP["hunyuan-video"]
    assert entry["comfyui_model_file"] == HUNYUAN_CKPT
    assert entry["video_backend"] == "hunyuan"
    assert resolve_video_backend("hunyuan-video") == "hunyuan"
    assert entry.get("default_enabled") is False

    entry15 = MODEL_MAP["hunyuan-video-1.5"]
    assert entry15["comfyui_model_file"] == HUNYUAN15_CKPT
    assert entry15["video_backend"] == "hunyuan"
    assert resolve_video_backend("hunyuan-video-1.5") == "hunyuan"
    assert entry15.get("default_enabled") is True


def test_build_hunyuan_defaults_720p_steps50():
    wf = build_hunyuan_video_workflow("rainy street", "blur", seed=1)
    class_types = {n.get("class_type") for n in wf.values()}
    assert "EmptyHunyuanVideo15Latent" in class_types
    assert "DualCLIPLoader" in class_types
    assert "VAELoader" in class_types
    assert "UNETLoader" in class_types
    sampler = next(n for n in wf.values() if n.get("class_type") == "KSampler")
    latent = next(n for n in wf.values() if n.get("class_type") == "EmptyHunyuanVideo15Latent")
    assert sampler["inputs"]["steps"] == HUNYUAN_DEFAULT_STEPS
    assert sampler["inputs"]["cfg"] == HUNYUAN15_CFG_DEFAULT
    assert latent["inputs"]["width"] == HUNYUAN_DEFAULT_WIDTH
    assert latent["inputs"]["height"] == HUNYUAN_DEFAULT_HEIGHT
    unet = next(n for n in wf.values() if n.get("class_type") == "UNETLoader")
    assert unet["inputs"]["unet_name"] == HUNYUAN15_CKPT
    dual = next(n for n in wf.values() if n.get("class_type") == "DualCLIPLoader")
    assert dual["inputs"]["type"] == "hunyuan_video_15"


def test_build_hunyuan_steps_override():
    wf = build_hunyuan_video_workflow("scene", "neg", seed=2, steps=30)
    sampler = next(n for n in wf.values() if n.get("class_type") == "KSampler")
    assert sampler["inputs"]["steps"] == 30


def test_build_hunyuan_distilled_and_cfg_and_cache():
    wf = build_hunyuan_video_workflow(
        "scene",
        "neg",
        seed=3,
        use_distilled=True,
        cfg_distilled=True,
        use_cache=True,
    )
    sampler = next(n for n in wf.values() if n.get("class_type") == "KSampler")
    assert sampler["inputs"]["steps"] == HUNYUAN15_DISTILLED_STEPS
    assert sampler["inputs"]["cfg"] == HUNYUAN15_CFG_DISTILLED
    assert any(n.get("class_type") == "MagCache" for n in wf.values())
    assert sampler["inputs"]["model"][0] == "74"


def test_build_hunyuan_legacy_13b():
    wf = build_hunyuan_video_workflow(
        "scene",
        "neg",
        seed=4,
        model_filename=HUNYUAN_CKPT,
    )
    class_types = {n.get("class_type") for n in wf.values()}
    assert "EmptyHunyuanLatentVideo" in class_types
    dual = next(n for n in wf.values() if n.get("class_type") == "DualCLIPLoader")
    assert dual["inputs"]["type"] == "hunyuan_video"
