#!/usr/bin/env python3
"""补验收：LTX2 I2V 真实出片 + PuLID/SeedVR2 结构（上传探针图）。"""
from __future__ import annotations

import base64
import json
import os
import sys
import time
import uuid
from pathlib import Path

import httpx

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
sys.path.insert(0, str(Path(__file__).resolve().parent))

from _agent_pipeline_e2e_probe import BASE, headers, login
from _plan_matrix_acceptance_probe import load_pulid_workflow_template
from providers.comfyui import _resolve_pulid_t5_encoder
from comfyui.client import build_seedvr2_image_enhance_workflow, upload_image_base64
from core.comfyui_settings import comfyui_http_url

OUT = Path("/root/autodl-tmp/logs/supplement_acceptance.json")
# 1x1 PNG
PROBE_PNG_B64 = (
    "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mP8z8BQDwAEhQGAhKmMIQAAAABJRU5ErkJggg=="
)


def load_credentials() -> tuple[str, str]:
    env_path = Path(__file__).resolve().parents[1] / ".env"
    password = "Admin@2026!"
    username = "seele"
    if env_path.is_file():
        for line in env_path.read_text(encoding="utf-8").splitlines():
            if line.startswith("SEED_ADMIN_PASSWORD="):
                password = line.split("=", 1)[1].strip().strip('"').strip("'")
    return username, password


def poll_task(client: httpx.Client, token: str, task_id: str, *, timeout: float) -> dict:
    deadline = time.time() + timeout
    last: dict = {}
    while time.time() < deadline:
        r = client.get(f"{BASE}/api/tasks/{task_id}", headers=headers(token), timeout=30)
        r.raise_for_status()
        last = r.json()
        if last.get("status") in ("completed", "failed"):
            return last
        time.sleep(5)
    raise TimeoutError(f"timeout task={task_id} last={last}")


async def ensure_probe_image() -> str:
    return await upload_image_base64(PROBE_PNG_B64)


def main() -> int:
    os.environ["AGENT_MOCK_GENERATION"] = "false"
    report: dict = {"ok": True, "cases": [], "timings": {}}

    def record(case: str, ok: bool, **extra):
        report["cases"].append({"case": case, "ok": ok, **extra})
        if not ok:
            report["ok"] = False
        mark = "PASS" if ok else "FAIL"
        print(f"[{mark}] {case}" + (f" — {extra.get('detail','')}" if extra.get("detail") else ""))

    import asyncio

    probe_face = asyncio.run(ensure_probe_image())
    probe_img = asyncio.run(ensure_probe_image())
    comfy_url = comfyui_http_url().rstrip("/")

    pulid_wf = load_pulid_workflow_template()
    if "49" in pulid_wf and pulid_wf["49"].get("class_type") == "LoadImage":
        pulid_wf["49"]["inputs"]["image"] = probe_face
    if "54" in pulid_wf and "text_encoder2" in pulid_wf["54"].get("inputs", {}):
        pulid_wf["54"]["inputs"]["text_encoder2"] = _resolve_pulid_t5_encoder()
    pr = httpx.post(f"{comfy_url}/prompt", json={"prompt": pulid_wf}, timeout=30)
    record("P2 flux-pulid ComfyUI structure", pr.status_code == 200, status=pr.status_code)

    img_wf = build_seedvr2_image_enhance_workflow(probe_img, upscale_factor=2.0)
    ir = httpx.post(f"{comfy_url}/prompt", json={"prompt": img_wf}, timeout=30)
    record("P3 SeedVR2 image structure", ir.status_code == 200, status=ir.status_code)

    with httpx.Client(timeout=120.0) as client:
        user, password = load_credentials()
        token = login(user, password)

        t0 = time.time()
        ri = client.post(
            f"{BASE}/api/tasks/image",
            headers=headers(token),
            json={
                "model": "flux-dev",
                "prompt": "portrait photo of a woman on a beach at sunset, cinematic lighting",
                "ratio": "16:9",
                "quality": "720P",
                "count": 1,
                "node_id": f"probe-ref-{uuid.uuid4().hex[:6]}",
            },
        )
        ref_url = None
        if ri.status_code == 200:
            ref_tid = ri.json().get("task_id") or (ri.json().get("task_ids") or [None])[0]
            ref_res = poll_task(client, token, ref_tid, timeout=300)
            ref_url = ref_res.get("result")
            report["timings"]["flux_ref_sec"] = round(time.time() - t0, 1)
            record(
                "P1 ref image for I2V",
                ref_res.get("status") == "completed" and bool(ref_url),
                url=(ref_url or "")[:80],
                error=ref_res.get("error"),
            )
        else:
            record("P1 ref image for I2V", False, detail=ri.text[:200])

        if ref_url:
            t0 = time.time()
            iv = client.post(
                f"{BASE}/api/tasks/video",
                headers=headers(token),
                json={
                    "model": "ltx2-fp4",
                    "prompt": "slow cinematic push in on subject at beach, golden hour",
                    "negative_prompt": "blurry, low quality",
                    "ratio": "16:9",
                    "resolution": "480P",
                    "duration": 5,
                    "generation_mode": "freeref",
                    "reference_image": ref_url,
                    "audio": False,
                    "node_id": f"probe-i2v-{uuid.uuid4().hex[:6]}",
                },
            )
            if iv.status_code != 200:
                record("P1 LTX2 I2V real", False, detail=iv.text[:200])
            else:
                tid = iv.json()["task_id"]
                print(f"  … polling LTX2 I2V task {tid}")
                result = poll_task(client, token, tid, timeout=900)
                elapsed = round(time.time() - t0, 1)
                report["timings"]["ltx2_i2v_sec"] = elapsed
                record(
                    "P1 LTX2 I2V real",
                    result.get("status") == "completed" and bool(result.get("result")),
                    elapsed_sec=elapsed,
                    error=result.get("error"),
                )

    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"\nReport: {OUT}")
    print(f"Overall: {'PASS' if report['ok'] else 'FAIL'}")
    return 0 if report["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
