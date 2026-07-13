"""Wan Fun Inpaint workflow 与 trace 单测（无 GPU）。"""

from __future__ import annotations

from comfyui.client import (
    WAN22_FUN_INPAINT_HIGH,
    WAN22_FUN_INPAINT_LOW,
    build_wan_fun_inpaint_workflow,
)
from trace_bus import extract_workflow_trace


def test_build_wan_fun_inpaint_workflow_nodes():
    wf = build_wan_fun_inpaint_workflow(
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
    assert "WanFunInpaintToVideo" in class_types
    assert "WanFirstLastFrameToVideo" not in class_types
    assert sum(1 for n in wf.values() if n.get("class_type") == "LoadImage") == 2
    unets = [
        n["inputs"]["unet_name"]
        for n in wf.values()
        if n.get("class_type") == "UNETLoader"
    ]
    assert WAN22_FUN_INPAINT_HIGH in unets
    assert WAN22_FUN_INPAINT_LOW in unets
    load_imgs = [
        n["inputs"]["image"]
        for n in wf.values()
        if n.get("class_type") == "LoadImage"
    ]
    assert load_imgs == ["start.png", "end.png"]


def test_build_wan_fun_inpaint_steps_split():
    wf = build_wan_fun_inpaint_workflow(
        "positive",
        "negative",
        "a.png",
        "b.png",
        duration_sec=3,
        seed=2,
        steps=8,
    )
    high = next(
        n
        for n in wf.values()
        if n.get("class_type") == "KSamplerAdvanced"
        and n["inputs"].get("add_noise") == "enable"
    )
    low = next(
        n
        for n in wf.values()
        if n.get("class_type") == "KSamplerAdvanced"
        and n["inputs"].get("add_noise") == "disable"
    )
    assert high["inputs"]["steps"] == 8
    assert high["inputs"]["end_at_step"] == 4
    assert low["inputs"]["start_at_step"] == 4
    assert low["inputs"]["end_at_step"] == 8


def test_extract_workflow_trace_fun_inpaint():
    wf = build_wan_fun_inpaint_workflow(
        "positive",
        "negative",
        "start_ref.png",
        "end_ref.png",
        duration_sec=3,
        seed=3,
    )
    trace = extract_workflow_trace(wf, WAN22_FUN_INPAINT_HIGH)
    assert trace["workflow_mode"] == "fun_inpaint"
    assert trace["start_reference_filename"] == "start_ref.png"
    assert trace["end_reference_filename"] == "end_ref.png"
    assert trace["positive_prompt"] == "positive"
    assert trace["negative_prompt"] == "negative"
    assert trace["num_frames"] is not None


def test_fun_inpaint_requires_both_frames():
    import pytest

    with pytest.raises(ValueError, match="首帧与尾帧"):
        build_wan_fun_inpaint_workflow("p", "n", "", "end.png", seed=1)
    with pytest.raises(ValueError, match="首帧与尾帧"):
        build_wan_fun_inpaint_workflow("p", "n", "start.png", "", seed=1)
