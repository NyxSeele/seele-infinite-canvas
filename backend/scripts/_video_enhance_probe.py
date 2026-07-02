#!/usr/bin/env python3
"""视频画质增强探针：API + workflow 注册 + mock 端到端。

前置：后端 :7788 + AGENT_MOCK_GENERATION=true；admin 登录。
退出码：0=PASS, 1=infra, 2=SKIP, 3=assert fail
"""
from __future__ import annotations

import sys
import uuid
from pathlib import Path

import httpx

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
sys.path.insert(0, str(Path(__file__).resolve().parent))

from _agent_pipeline_e2e_probe import BASE, headers, login
from _mock_generation_acceptance import poll_task
from comfyui.client import (
    build_realesrgan_enhance_workflow,
    build_seedvr2_enhance_workflow,
)
from model_registry import (
    VIDEO_ENHANCE_REALESRGAN_ID,
    VIDEO_ENHANCE_SEEDVR2_ID,
    get_comfyui_provider,
    resolve_video_enhance_workflow,
)


def submit_mock_video(client: httpx.Client, token: str) -> str:
    r = client.post(
        f"{BASE}/api/tasks/video",
        headers=headers(token),
        json={
            "model": "ltx-video",
            "prompt": "video enhance probe seed",
            "ratio": "16:9",
            "resolution": "720P",
            "duration": 5,
            "count": 1,
            "node_id": f"probe-ve-seed-{uuid.uuid4().hex[:8]}",
        },
        timeout=30,
    )
    r.raise_for_status()
    task_id = r.json()["task_id"]
    result = poll_task(client, token, task_id, timeout=30)
    assert result["status"] == "completed", result
    url = result.get("result")
    assert url, result
    return url


def assert_workflow_builders() -> None:
    seed = build_seedvr2_enhance_workflow(
        "probe_input.mp4",
        upscale_factor=1.0,
        input_noise_scale=0.3,
        batch_size=16,
        color_correction="none",
        model_size="3b",
        strength="sharp",
        source_height=720,
    )
    classes = {n.get("class_type") for n in seed.values()}
    assert "VHS_LoadVideo" in classes, classes
    assert "SeedVR2VideoUpscaler" in classes, classes
    assert "VHS_VideoCombine" in classes, classes
    upscaler = next(n for n in seed.values() if n.get("class_type") == "SeedVR2VideoUpscaler")
    inputs = upscaler.get("inputs") or {}
    assert inputs.get("input_noise_scale") == 0.3, inputs
    assert inputs.get("batch_size") == 16, inputs
    assert inputs.get("color_correction") == "none", inputs
    assert inputs.get("resolution") == 720, inputs

    realesr = build_realesrgan_enhance_workflow("probe_input.mp4", upscale_factor=2.0)
    classes2 = {n.get("class_type") for n in realesr.values()}
    assert "UpscaleModelLoader" in classes2, classes2
    assert "ImageUpscaleWithModel" in classes2, classes2


def assert_registry_disabled() -> None:
    seed = get_comfyui_provider(VIDEO_ENHANCE_SEEDVR2_ID)
    real = get_comfyui_provider(VIDEO_ENHANCE_REALESRGAN_ID)
    assert seed is not None, "missing seedvr2 provider"
    assert real is not None, "missing realesrgan provider"
    assert seed.get("enabled") is False, seed
    assert real.get("enabled") is False, real
    assert resolve_video_enhance_workflow("auto") is None


def assert_503_when_disabled(client: httpx.Client, token: str) -> None:
    """非 mock 环境下 provider 全 disabled 应 503（本探针在 mock 下跳过）。"""
    import os

    if os.environ.get("AGENT_MOCK_GENERATION", "").lower() in ("1", "true", "yes"):
        print("[503] skip — mock mode allows enhance without enabled providers")
        return
    r = client.post(
        f"{BASE}/api/tasks/video-enhance",
        headers=headers(token),
        json={
            "video_url": "/api/uploads/videos/nonexistent.mp4",
            "upscale_factor": 2.0,
            "workflow": "auto",
            "node_id": "probe-ve-503",
        },
        timeout=15,
    )
    assert r.status_code == 503, r.status_code


def main() -> int:
    try:
        assert_workflow_builders()
        assert_registry_disabled()
        print("[builders] OK")
        print("[registry] providers registered, enabled=False")
    except AssertionError as exc:
        print(f"[assert] {exc}")
        return 3

    with httpx.Client() as client:
        try:
            token = login("admin", "Admin@2026!")
        except Exception as exc:
            print(f"[infra] login failed: {exc}")
            return 1

        try:
            video_url = submit_mock_video(client, token)
            print(f"[seed-video] {video_url[:80]}...")

            rec = client.post(
                f"{BASE}/api/tasks/video-enhance/recommend-params",
                headers=headers(token),
                json={"video_url": video_url},
                timeout=30,
            )
            rec.raise_for_status()
            rec_body = rec.json()
            params = rec_body.get("params") or {}
            reasoning = rec_body.get("reasoning") or ""
            assert params, rec_body
            assert reasoning, rec_body
            assert params.get("upscale_factor") in (1.0, 1.5, 2.0, 3.0), params
            assert params.get("batch_size") in (4, 8, 16), params
            print(f"[recommend] upscale={params.get('upscale_factor')} reasoning={reasoning[:60]}")

            r = client.post(
                f"{BASE}/api/tasks/video-enhance",
                headers=headers(token),
                json={
                    "video_url": video_url,
                    "upscale_factor": params.get("upscale_factor", 2.0),
                    "strength": params.get("strength", "normal"),
                    "workflow": "auto",
                    "input_noise_scale": params.get("input_noise_scale", 0.25),
                    "batch_size": params.get("batch_size", 8),
                    "color_correction": params.get("color_correction", "lab"),
                    "model_size": params.get("model_size", "7b"),
                    "node_id": "probe-video-enhance",
                },
                timeout=30,
            )
            r.raise_for_status()
            body = r.json()
            task_id = body["task_id"]
            assert body.get("comfy_prompt_id") == "mock", body
            print(f"[submit] task_id={task_id}")

            result = poll_task(client, token, task_id, timeout=30)
            assert result["status"] == "completed", result
            assert "/api/uploads/videos/" in (result.get("result") or ""), result
            print(f"[poll] completed result={result['result'][:80]}...")

            assert_503_when_disabled(client, token)
        except httpx.ConnectError:
            print("[infra] backend not reachable")
            return 1
        except AssertionError as exc:
            print(f"[assert] {exc}")
            return 3
        except Exception as exc:
            print(f"[infra] {exc}")
            return 1

    print("PASS video_enhance_probe")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
