#!/usr/bin/env python3
"""视频首尾帧模式探针：generation_mode=keyframe + first/last frame URL。

前置：后端 :7788 + AGENT_MOCK_GENERATION=true；admin 登录。
会先 mock 出图取得真实 uploads URL 作为首尾帧。

注意：mock 仅验证 API 提交；真实 GPU 首尾帧见 scripts/_prompt_debug_phase3_keyframe.py。
退出码：0=PASS, 1=infra, 3=assert fail
"""
from __future__ import annotations

import sys
import uuid
from pathlib import Path

import httpx

sys.path.insert(0, str(Path(__file__).resolve().parent))

from _agent_pipeline_e2e_probe import BASE, headers, login
from _mock_generation_acceptance import poll_task


def submit_mock_image(client: httpx.Client, token: str) -> str:
    r = client.post(
        f"{BASE}/api/tasks/image",
        headers=headers(token),
        json={
            "model": "stable-diffusion",
            "prompt": "keyframe probe seed frame",
            "ratio": "16:9",
            "quality": "2K",
            "count": 1,
            "node_id": f"probe-kf-seed-{uuid.uuid4().hex[:8]}",
        },
        timeout=30,
    )
    r.raise_for_status()
    task_id = r.json()["task_id"]
    result = poll_task(client, token, task_id, timeout=20)
    assert result["status"] == "completed", result
    url = result.get("result")
    assert url, result
    return url


def main() -> int:
    with httpx.Client() as client:
        try:
            token = login("admin", "Admin@2026!")
        except Exception as exc:
            print(f"[infra] login failed: {exc}")
            return 1

        frame_url = submit_mock_image(client, token)
        print(f"[seed-frame] {frame_url[:80]}...")

        r = client.post(
            f"{BASE}/api/tasks/video",
            headers=headers(token),
            json={
                "model": "ltx-video",
                "prompt": "keyframe mode probe: panda turns head",
                "generation_mode": "keyframe",
                "ratio": "16:9",
                "resolution": "720P",
                "duration": 5,
                "count": 1,
                "node_id": "probe-keyframe-video",
                "first_frame": frame_url,
                "last_frame": frame_url,
            },
            timeout=30,
        )
        r.raise_for_status()
        body = r.json()
        task_id = body["task_id"]
        assert body.get("comfy_prompt_id") == "mock", body
        print(f"[submit] task_id={task_id} mode=keyframe")

        result = poll_task(client, token, task_id, timeout=20)
        assert result["status"] == "completed", result
        assert result.get("result"), result
        assert "/api/uploads/videos/" in result["result"]
        print(f"[completed] result={result['result'][:80]}...")

    print("PASS: video keyframe mode probe")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except AssertionError as exc:
        print(f"FAIL: {exc}", file=sys.stderr)
        raise SystemExit(3) from exc
    except Exception as exc:
        print(f"FAIL: {exc}", file=sys.stderr)
        raise SystemExit(1) from exc
