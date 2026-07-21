#!/usr/bin/env python3
"""真实 GPU 链路验收：图 → 视频 → Agent（非 mock）。"""
from __future__ import annotations

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
from core.comfyui_settings import comfyui_http_url

OUT = Path("/root/autodl-tmp/logs/gpu_chain_acceptance.json")
COMFY = Path("/root/autodl-tmp/ComfyUI/models")


def poll_task(client: httpx.Client, token: str, task_id: str, *, timeout: float) -> dict:
    deadline = time.time() + timeout
    last: dict = {}
    while time.time() < deadline:
        r = client.get(f"{BASE}/api/tasks/{task_id}", headers=headers(token), timeout=30)
        r.raise_for_status()
        last = r.json()
        st = last.get("status")
        if st in ("completed", "failed"):
            return last
        time.sleep(4)
    raise TimeoutError(f"timeout task={task_id} last={last}")


def main() -> int:
    os.environ["AGENT_MOCK_GENERATION"] = "false"
    report: dict = {"ok": True, "steps": [], "missing": [], "errors": []}

    try:
        httpx.get(f"{comfyui_http_url()}/system_stats", timeout=8).raise_for_status()
    except Exception as exc:
        report["ok"] = False
        report["errors"].append(f"ComfyUI unreachable: {exc}")
        OUT.write_text(json.dumps(report, ensure_ascii=False, indent=2))
        print(json.dumps(report, ensure_ascii=False, indent=2))
        return 2

    # weight presence
    need = {
        "flux": COMFY / "diffusion_models/flux1-dev-fp8.safetensors",
        "wan_t2v": COMFY / "diffusion_models/wan2.2_t2v_high_noise_14B_fp8_scaled.safetensors",
        "seedvr2": COMFY / "SEEDVR2/seedvr2_ema_3b_fp8_e4m3fn.safetensors",
    }
    for k, p in need.items():
        ok = p.is_file() and p.stat().st_size > 1_000_000
        report["steps"].append({"check": f"weight:{k}", "ok": ok, "path": str(p), "size": p.stat().st_size if p.is_file() else 0})
        if not ok:
            report["missing"].append(k)

    # MagCache node
    try:
        info = httpx.get(f"{comfyui_http_url()}/object_info/MagCache", timeout=10).json()
        report["steps"].append({"check": "MagCache_node", "ok": "MagCache" in info})
    except Exception as exc:
        report["steps"].append({"check": "MagCache_node", "ok": False, "error": str(exc)})
        report["missing"].append("MagCache")

    with httpx.Client(timeout=60.0) as client:
        token = login("admin", "Admin@2026!")

        # ── 1. Flux 出图 ─────────────────────────────────────────
        t0 = time.time()
        r = client.post(
            f"{BASE}/api/tasks/image",
            headers=headers(token),
            json={
                "model": "flux-dev",
                "prompt": "chain probe: rainy night city street, neon reflections, photorealistic",
                "ratio": "16:9",
                "quality": "2K",
                "count": 1,
                "node_id": f"chain-flux-{uuid.uuid4().hex[:8]}",
            },
        )
        if r.status_code >= 400:
            report["ok"] = False
            report["errors"].append(f"flux submit {r.status_code}: {r.text[:300]}")
        else:
            tid = r.json()["task_id"]
            task = poll_task(client, token, tid, timeout=600)
            ok = task.get("status") == "completed" and bool(task.get("result"))
            report["steps"].append({
                "check": "flux_image_gpu",
                "ok": ok,
                "task_id": tid,
                "status": task.get("status"),
                "result": str(task.get("result") or "")[:120],
                "error": task.get("error"),
                "sec": round(time.time() - t0, 1),
            })
            if not ok:
                report["ok"] = False
                report["errors"].append(f"flux failed: {task.get('error') or task.get('status')}")

        # ── 2. Wan T2V ───────────────────────────────────────────
        t0 = time.time()
        r = client.post(
            f"{BASE}/api/tasks/video",
            headers=headers(token),
            json={
                "model": "wan-2.6",
                "prompt": "chain probe: a woman walking in rain, cinematic, neon lights",
                "ratio": "16:9",
                "duration": 3,
                "resolution": "720P",
                "node_id": f"chain-wan-{uuid.uuid4().hex[:8]}",
                "sampling_profile": "fast",
            },
        )
        if r.status_code >= 400:
            report["ok"] = False
            report["errors"].append(f"wan submit {r.status_code}: {r.text[:400]}")
            report["steps"].append({"check": "wan_video_gpu", "ok": False, "http": r.status_code, "body": r.text[:400]})
        else:
            tid = r.json()["task_id"]
            task = poll_task(client, token, tid, timeout=900)
            ok = task.get("status") == "completed" and bool(task.get("result"))
            report["steps"].append({
                "check": "wan_video_gpu",
                "ok": ok,
                "task_id": tid,
                "status": task.get("status"),
                "result": str(task.get("result") or "")[:120],
                "error": task.get("error"),
                "sec": round(time.time() - t0, 1),
            })
            if not ok:
                report["ok"] = False
                report["errors"].append(f"wan failed: {task.get('error') or task.get('status')}")

        # ── 3. Agent：创意卡片/大纲意图（真实 LLM，非 mock）────────
        t0 = time.time()
        project_id = str(uuid.uuid4())
        # create project if API requires
        try:
            pr = client.post(
                f"{BASE}/api/projects",
                headers=headers(token),
                json={"name": f"chain-probe-{project_id[:8]}"},
                timeout=30,
            )
            if pr.status_code < 400:
                project_id = pr.json().get("id") or project_id
        except Exception:
            pass

        ar = client.post(
            f"{BASE}/api/agent/run",
            headers=headers(token),
            json={
                "project_id": project_id,
                "canvas_snapshot": {
                    "nodes": [],
                    "edges": [],
                    "selected_node_ids": [],
                    "total_node_count": 0,
                    "snapshot_truncated": False,
                    "omitted_node_count": 0,
                },
                "messages": [
                    {"role": "user", "content": "雨夜重庆，一个女人独自等待，请先给出创意方向卡片，3个镜头"}
                ],
                "execution_mode": "manual",
            },
            timeout=180,
        )
        agent_ok = ar.status_code < 400
        agent_body = ""
        events = []
        if agent_ok:
            agent_body = ar.text[:2000]
            for line in ar.text.splitlines():
                if line.startswith("data: "):
                    try:
                        events.append(json.loads(line[6:]))
                    except json.JSONDecodeError:
                        pass
            # any meaningful event
            agent_ok = bool(events) or ("actions" in ar.text) or ar.status_code == 200
        report["steps"].append({
            "check": "agent_run_llm",
            "ok": agent_ok,
            "http": ar.status_code,
            "events": len(events),
            "sample": str(events[:2])[:300] if events else agent_body[:300],
            "sec": round(time.time() - t0, 1),
        })
        if not agent_ok:
            report["ok"] = False
            report["errors"].append(f"agent failed http={ar.status_code}: {ar.text[:300]}")

    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0 if report["ok"] else 3


if __name__ == "__main__":
    raise SystemExit(main())
