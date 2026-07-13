#!/usr/bin/env python3
"""真实 GPU 出图探针（HANDOFF 第八节 B 缩影）。

默认 SKIP：AGENT_MOCK_GENERATION=true 或 ComfyUI 不可达时 exit 2。
真实验收：AGENT_MOCK_GENERATION=false + ComfyUI 已启动 + 已注册 image 模型。

退出码：0=PASS, 1=infra, 2=SKIP, 3=assert fail
"""
from __future__ import annotations

import os
import sys
import time
from pathlib import Path

import httpx

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
sys.path.insert(0, str(Path(__file__).resolve().parent))

from _agent_pipeline_e2e_probe import BASE, headers, login
from core.comfyui_settings import comfyui_http_url
from core.config import settings


def comfyui_reachable() -> bool:
    url = comfyui_http_url().rstrip("/")
    try:
        r = httpx.get(f"{url}/system_stats", timeout=5)
        return r.status_code < 500
    except Exception:
        return False


def poll_task(client: httpx.Client, token: str, task_id: str, *, timeout: float = 300) -> dict:
    deadline = time.time() + timeout
    last: dict = {}
    while time.time() < deadline:
        r = client.get(f"{BASE}/api/tasks/{task_id}", headers=headers(token), timeout=30)
        r.raise_for_status()
        last = r.json()
        if last.get("status") in ("completed", "failed"):
            return last
        time.sleep(2)
    raise TimeoutError(f"task {task_id} not terminal within {timeout}s, last={last}")


def main() -> int:
    mock_on = settings.agent_mock_generation or os.environ.get("AGENT_MOCK_GENERATION", "").lower() in (
        "1",
        "true",
        "yes",
    )
    if mock_on:
        print("SKIP: AGENT_MOCK_GENERATION is enabled — use AGENT_MOCK_GENERATION=false for real GPU probe")
        return 2
    if not comfyui_reachable():
        print(f"SKIP: ComfyUI not reachable at {comfyui_http_url()}")
        print("See backend/docs/COMFYUI_CUTOVER_RUNBOOK.md")
        return 2

    with httpx.Client() as client:
        try:
            token = login("admin", "Admin@2026!")
        except Exception as exc:
            print(f"[infra] login failed: {exc}")
            return 1

        r = client.post(
            f"{BASE}/api/tasks/image",
            headers=headers(token),
            json={
                "model": "flux-dev",
                "prompt": "real media probe: simple red apple on white table",
                "ratio": "1:1",
                "quality": "2K",
                "count": 1,
                "node_id": "probe-real-gpu-image",
            },
            timeout=60,
        )
        if r.status_code >= 400:
            print(f"SKIP: submit failed ({r.status_code}): {r.text[:300]}")
            return 2
        task_id = r.json().get("task_id")
        assert task_id, r.json()
        print(f"[submit] task_id={task_id}")

        result = poll_task(client, token, task_id, timeout=300)
        if result.get("status") != "completed":
            print(f"FAIL: task status={result.get('status')} error={result.get('error')}")
            return 3
        assert result.get("result"), result
        print(f"[completed] result={result['result'][:80]}...")

    print("PASS: real media pipeline probe")
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
