#!/usr/bin/env python3
"""LUT 调色探针：内置资产 + API + mock video-lut 端到端。

前置：后端 :7788 + AGENT_MOCK_GENERATION=true；admin 登录。
退出码：0=PASS, 1=infra, 2=SKIP, 3=assert fail
"""
from __future__ import annotations

import os
import sys
import uuid
from pathlib import Path

import httpx

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
sys.path.insert(0, str(Path(__file__).resolve().parent))

from _agent_pipeline_e2e_probe import BASE, headers, login
from _mock_generation_acceptance import poll_task
from services.lut_registry import LUT_ASSETS_DIR, list_builtin_presets, resolve_builtin_lut_path


def create_probe_project(
    client: httpx.Client, token: str, script_table_id: str
) -> str:
    r = client.post(
        f"{BASE}/api/canvas/projects",
        headers=headers(token),
        json={
            "name": f"probe-lut-{uuid.uuid4().hex[:8]}",
            "canvas_data": {
                "nodes": [
                    {
                        "id": script_table_id,
                        "type": "script-table",
                        "position": {"x": 0, "y": 0},
                        "data": {"rows": [], "lutPreset": "warm_orange_film"},
                    }
                ],
                "edges": [],
            },
        },
        timeout=30,
    )
    r.raise_for_status()
    return r.json()["id"]


def assert_builtin_luts() -> None:
    presets = list_builtin_presets()
    assert len(presets) >= 6, presets
    for pid in ("cool_teal", "warm_orange_film", "natural_realistic"):
        path = resolve_builtin_lut_path(pid)
        assert path and path.is_file(), pid
    assert (LUT_ASSETS_DIR / "cool_teal.cube").stat().st_size > 1000


def submit_mock_video(client: httpx.Client, token: str, node_id: str) -> str:
    r = client.post(
        f"{BASE}/api/tasks/video",
        headers=headers(token),
        json={
            "model": "ltx-video",
            "prompt": "lut probe seed",
            "ratio": "16:9",
            "resolution": "720P",
            "duration": 5,
            "count": 1,
            "node_id": node_id,
        },
        timeout=30,
    )
    r.raise_for_status()
    task_id = r.json()["task_id"]
    result = poll_task(client, token, task_id, timeout=60)
    assert result["status"] == "completed", result
    url = result.get("result")
    assert url, result
    return url


def main() -> int:
    try:
        assert_builtin_luts()
    except AssertionError as e:
        print(f"LUT assets FAIL: {e}")
        return 3

    password = (
        os.environ.get("PROBE_PASSWORD")
        or os.environ.get("SEED_ADMIN_PASSWORD")
        or ""
    ).strip()
    if not password:
        print("LUT probe infra FAIL: set SEED_ADMIN_PASSWORD or PROBE_PASSWORD")
        return 1
    try:
        token = login("admin", password)
    except Exception as e:
        print(f"LUT probe infra FAIL: {e}")
        return 1

    script_table_id = f"st-{uuid.uuid4().hex[:8]}"

    try:
        with httpx.Client(base_url=BASE, timeout=60) as client:
            project_id = create_probe_project(client, token, script_table_id)
            video_node_id = f"vid-{uuid.uuid4().hex[:8]}"
            r = client.get(
                f"/api/projects/{project_id}/lut",
                headers=headers(token),
                params={"script_table_node_id": script_table_id},
            )
            r.raise_for_status()
            cfg = r.json()
            assert cfg.get("lut_preset") == "warm_orange_film", cfg

            video_url = submit_mock_video(client, token, video_node_id)

            r = client.post(
                f"{BASE}/api/tasks/video-lut",
                headers=headers(token),
                json={
                    "project_id": project_id,
                    "script_table_node_id": script_table_id,
                    "video_url": video_url,
                    "node_id": video_node_id,
                },
            )
            r.raise_for_status()
            lut_task_id = r.json()["task_id"]
            lut_result = poll_task(client, token, lut_task_id, timeout=90)
            assert lut_result["status"] == "completed", lut_result
            out_url = lut_result.get("result")
            assert out_url, lut_result

            rel = out_url.split("/videos/")[-1].split("?")[0]
            out_path = Path(__file__).resolve().parents[1] / "uploads" / "videos" / rel
            assert out_path.is_file() and out_path.stat().st_size > 0, out_path

            r = client.post(
                f"/api/projects/{project_id}/lut/apply-all",
                headers=headers(token),
                json={"script_table_node_id": script_table_id},
            )
            r.raise_for_status()
            apply_body = r.json()
            assert apply_body.get("queued", 0) >= 0, apply_body

        print("LUT probe PASS")
        return 0
    except AssertionError as e:
        print(f"LUT probe ASSERT FAIL: {e}")
        return 3
    except httpx.HTTPError as e:
        print(f"LUT probe HTTP FAIL: {e}")
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
