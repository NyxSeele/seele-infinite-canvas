"""Workflow registry submit/load integration tests (no real GPU)."""

from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock, patch

import pytest

from comfyui import client
from comfyui.workflow_registry import load_workflow_template


def test_load_non_ltx_enhance_keys():
    for key in (
        "video_enhance_seedvr2.json",
        "video_enhance_realesrgan.json",
        "flux_pulid_reactor.json",
    ):
        payload = load_workflow_template(key)
        assert isinstance(payload, dict)
        assert payload
        assert any(isinstance(node, dict) and "class_type" in node for node in payload.values())


def test_build_seedvr2_enhance_from_registry():
    wf = client.build_seedvr2_enhance_workflow("clip.mp4", strength="normal")
    assert wf["1"]["inputs"]["video"] == "clip.mp4"
    assert wf["2"]["class_type"] == "SeedVR2LoadDiTModel"
    assert wf["2"]["inputs"]["model"] == client.SEEDVR2_DIT_NORMAL


def test_build_realesrgan_enhance_from_registry():
    wf = client.build_realesrgan_enhance_workflow("clip.mp4")
    assert wf["1"]["inputs"]["video"] == "clip.mp4"
    assert wf["2"]["inputs"]["model_name"] == client.REALESRGAN_MODEL


def test_submit_by_workflow_key_image_path():
    async def fake_post(workflow, client_id, **kwargs):
        assert workflow["999"]["class_type"] == "OverrideNode"
        return "pid-1", "cid-1", "http://127.0.0.1:8188"

    async def run():
        with patch.object(client, "_post_workflow", new=AsyncMock(side_effect=fake_post)):
            prompt_id, client_id, node_url = await client.submit_by_workflow_key(
                "video_enhance_realesrgan.json",
                patch_fn=lambda wf: {**wf, "999": {"class_type": "OverrideNode", "inputs": {}}},
            )
        assert prompt_id == "pid-1"
        assert client_id == "cid-1"
        assert node_url.endswith("8188")

    asyncio.run(run())


def test_submit_by_workflow_key_video_path():
    async def fake_video_post(workflow, **kwargs):
        assert workflow["1"]["class_type"] == "VHS_LoadVideo"
        return "pid-2", "cid-2", workflow, "http://127.0.0.1:8188"

    async def run():
        with patch.object(client, "_log_and_post_video_workflow", new=AsyncMock(side_effect=fake_video_post)):
            result = await client.submit_by_workflow_key(
                "video_enhance_seedvr2.json",
                as_video=True,
                backend="seedvr2_enhance",
            )
        assert result[0] == "pid-2"

    asyncio.run(run())
