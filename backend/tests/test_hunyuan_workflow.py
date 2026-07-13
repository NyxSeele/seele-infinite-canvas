"""HunyuanVideo workflow unit tests (no GPU)."""

from __future__ import annotations

from comfyui.client import (
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


def test_build_hunyuan_defaults_720p_steps50():
    wf = build_hunyuan_video_workflow("rainy street", "blur", seed=1)
    class_types = {n.get("class_type") for n in wf.values()}
    assert "EmptyHunyuanLatentVideo" in class_types
    assert "DualCLIPLoader" in class_types
    assert "VAELoader" in class_types
    assert "UNETLoader" in class_types
    sampler = next(n for n in wf.values() if n.get("class_type") == "KSampler")
    latent = next(n for n in wf.values() if n.get("class_type") == "EmptyHunyuanLatentVideo")
    assert sampler["inputs"]["steps"] == HUNYUAN_DEFAULT_STEPS
    assert latent["inputs"]["width"] == HUNYUAN_DEFAULT_WIDTH
    assert latent["inputs"]["height"] == HUNYUAN_DEFAULT_HEIGHT
    unet = next(n for n in wf.values() if n.get("class_type") == "UNETLoader")
    assert unet["inputs"]["unet_name"] == HUNYUAN_CKPT


def test_build_hunyuan_steps_override():
    wf = build_hunyuan_video_workflow("scene", "neg", seed=2, steps=30)
    sampler = next(n for n in wf.values() if n.get("class_type") == "KSampler")
    assert sampler["inputs"]["steps"] == 30
