#!/usr/bin/env python3
"""§八 B GPU 验收缩影：Flux 出图 → Wan 结构探针 → SeedVR2 workflow 探针。"""
from __future__ import annotations

import os
import subprocess
import sys
import time
from pathlib import Path

import httpx

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
sys.path.insert(0, str(Path(__file__).resolve().parent))

from _agent_pipeline_e2e_probe import BASE, headers, login
from core.comfyui_settings import comfyui_http_url

COMFY = Path("/root/autodl-tmp/ComfyUI/models")
BACKEND = Path(__file__).resolve().parents[1]


def file_ok(path: Path, min_mb: int) -> bool:
    return path.is_file() and path.stat().st_size >= min_mb * 1024 * 1024


def poll_task(client: httpx.Client, token: str, task_id: str, *, timeout: float = 600) -> dict:
    deadline = time.time() + timeout
    last: dict = {}
    while time.time() < deadline:
        r = client.get(f"{BASE}/api/tasks/{task_id}", headers=headers(token), timeout=30)
        r.raise_for_status()
        last = r.json()
        if last.get("status") in ("completed", "failed"):
            return last
        time.sleep(3)
    raise TimeoutError(f"task {task_id} timeout, last={last}")


def main() -> int:
    if os.environ.get("AGENT_MOCK_GENERATION", "").lower() in ("1", "true", "yes"):
        print("SKIP: mock mode")
        return 2
    try:
        httpx.get(f"{comfyui_http_url().rstrip('/')}/system_stats", timeout=5).raise_for_status()
    except Exception as exc:
        print(f"SKIP: ComfyUI unreachable: {exc}")
        return 2

    results: list[str] = []
    exit_code = 0

    with httpx.Client() as client:
        token = login("admin", "Admin@2026!")

        if file_ok(COMFY / "diffusion_models/flux1-dev-fp8.safetensors", 1000):
            r = client.post(
                f"{BASE}/api/tasks/image",
                headers=headers(token),
                json={
                    "model": "flux-dev",
                    "prompt": "cinematic portrait, soft natural light, photorealistic",
                    "ratio": "16:9",
                    "quality": "2K",
                    "count": 1,
                    "node_id": "probe-8b-flux",
                },
                timeout=60,
            )
            if r.status_code >= 400:
                print(f"FAIL flux submit: {r.status_code} {r.text[:200]}")
                return 3
            task = poll_task(client, token, r.json()["task_id"], timeout=600)
            if task.get("status") != "completed":
                print(f"FAIL flux: {task}")
                return 3
            results.append(f"flux OK: {str(task.get('result'))[:60]}")
        else:
            results.append("flux SKIP: weights missing")

    wan_high = COMFY / "diffusion_models/wan2.2_t2v_high_noise_14B_fp8_scaled.safetensors"
    if file_ok(wan_high, 1000):
        proc = subprocess.run(
            [sys.executable, str(BACKEND / "scripts/_comfyui_workflow_structure_probe.py"), "--model", "wan"],
            cwd=str(BACKEND),
            capture_output=True,
            text=True,
            timeout=120,
        )
        if proc.returncode != 0:
            print(proc.stdout)
            print(proc.stderr, file=sys.stderr)
            print("FAIL wan structure probe")
            return 3
        results.append("wan structure OK")
    else:
        results.append("wan SKIP: weights missing")

    seed_dit = COMFY / "SEEDVR2/seedvr2_ema_3b_fp8_e4m3fn.safetensors"
    if file_ok(seed_dit, 500):
        from scripts._video_enhance_probe import assert_registry_providers, assert_workflow_builders

        assert_workflow_builders()
        assert_registry_providers()
        results.append("seedvr2 workflow/registry OK")
    else:
        results.append("seedvr2 SKIP: weights missing")
        exit_code = 1

    for line in results:
        print(line)
    if any("FAIL" in line for line in results):
        return 3
    if any("SKIP" in line for line in results):
        print("PARTIAL: some weights still downloading")
        return exit_code or 1
    print("PASS §八B acceptance")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
