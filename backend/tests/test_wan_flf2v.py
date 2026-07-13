"""Wan FLF2V workflow 与 trace 单测。"""

from __future__ import annotations

from comfyui.client import build_wan_flf2v_workflow, build_wan_i2v_workflow
from trace_bus import extract_workflow_trace


def test_build_wan_flf2v_workflow_nodes():
    wf = build_wan_flf2v_workflow(
        "camera pulls back",
        "low quality",
        "start.png",
        "end.png",
        width=1280,
        height=720,
        duration_sec=3,
        seed=1,
    )
    class_types = {n.get("class_type") for n in wf.values() if isinstance(n, dict)}
    assert "WanFirstLastFrameToVideo" in class_types
    assert sum(1 for n in wf.values() if n.get("class_type") == "LoadImage") == 2
    assert "WanImageToVideo" not in class_types


def test_extract_workflow_trace_flf2v():
    wf = build_wan_flf2v_workflow(
        "positive",
        "negative",
        "start_ref.png",
        "end_ref.png",
        duration_sec=3,
        seed=2,
    )
    trace = extract_workflow_trace(wf, "wan2.2_i2v_high_noise_14B_fp8_scaled.safetensors")
    assert trace["workflow_mode"] == "flf2v"
    assert trace["start_reference_filename"] == "start_ref.png"
    assert trace["end_reference_filename"] == "end_ref.png"
    assert trace["positive_prompt"] == "positive"
    assert trace["negative_prompt"] == "negative"
    assert trace["num_frames"] is not None


def test_extract_workflow_trace_i2v_regression():
    wf = build_wan_i2v_workflow(
        "positive",
        "negative",
        "only.png",
        duration_sec=3,
        seed=3,
    )
    trace = extract_workflow_trace(wf, "wan2.2_i2v_high_noise_14B_fp8_scaled.safetensors")
    assert trace["workflow_mode"] == "image2video"
    assert trace["reference_filename"] == "only.png"


def test_g31_i2v_quality_steps_split():
    wf = build_wan_i2v_workflow(
        "The camera slowly dollies in",
        "low quality",
        "ref.png",
        duration_sec=3,
        seed=7,
        steps=8,
    )
    high = next(n for n in wf.values() if n.get("class_type") == "KSamplerAdvanced" and n["inputs"].get("add_noise") == "enable")
    low = next(n for n in wf.values() if n.get("class_type") == "KSamplerAdvanced" and n["inputs"].get("add_noise") == "disable")
    assert high["inputs"]["steps"] == 8
    assert high["inputs"]["end_at_step"] == 4
    assert low["inputs"]["start_at_step"] == 4
    assert low["inputs"]["end_at_step"] == 8


def test_g31_resolve_wan_steps():
    from comfyui.client import resolve_wan_steps

    assert resolve_wan_steps("fast") == 4
    assert resolve_wan_steps("quality") == 8
    assert resolve_wan_steps(steps=6) == 6
