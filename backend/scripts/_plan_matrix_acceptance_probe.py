#!/usr/bin/env python3
"""计划矩阵逐项验收：P0–P4 + LTX2 真实出片（非 mock）。"""
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
from comfyui.client import (
    build_ltx2_fp4_i2v_workflow,
    build_ltx2_fp4_t2v_workflow,
    build_seedvr2_image_enhance_workflow,
)
from core.comfyui_settings import comfyui_http_url
from model_registry import COMFYUI_PROVIDER_MAP, IMAGE_ENHANCE_SEEDVR2_ID

OUT = Path("/root/autodl-tmp/logs/plan_matrix_acceptance.json")
PROMPT = "cinematic slow dolly shot, golden hour sunlight over calm ocean, film grain, 24fps"
NEG = "blurry, low quality, watermark"
FLF_FIRST = "data:image/png;base64,iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mP8z8BQDwAEhQGAhKmMIQAAAABJRU5ErkJggg=="
FLF_LAST = "data:image/png;base64,iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mNk+M9QDwADhgGAWjR9awAAAABJRU5ErkJggg=="


def task_model_id_from_db(task_id: str) -> str | None:
    from sqlalchemy import create_engine, text

    from core.config import settings

    engine = create_engine(settings.database_url)
    with engine.connect() as conn:
        row = conn.execute(
            text("SELECT model_id FROM tasks WHERE id = :id"),
            {"id": task_id},
        ).fetchone()
    return row[0] if row else None


def load_pulid_workflow_template() -> dict:
    path = (
        Path(__file__).resolve().parents[1]
        / "comfyui/workflows/flux_pulid_reactor.json"
    )
    raw = json.loads(path.read_text(encoding="utf-8"))
    return {k: v for k, v in raw.items() if isinstance(v, dict) and "class_type" in v}


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


def post_video(client, token, **kwargs) -> dict:
    body = {
        "model": "ltx2-fp4",
        "prompt": PROMPT,
        "negative_prompt": NEG,
        "ratio": "16:9",
        "resolution": "480P",
        "duration": 5,
        "node_id": f"probe-{uuid.uuid4().hex[:8]}",
        **kwargs,
    }
    r = client.post(f"{BASE}/api/tasks/video", headers=headers(token), json=body, timeout=120)
    return {"status_code": r.status_code, "body": r.json() if r.content else {}}


def main() -> int:
    os.environ["AGENT_MOCK_GENERATION"] = "false"
    report: dict = {"ok": True, "cases": [], "timings": {}}

    def record(case: str, ok: bool, **extra):
        report["cases"].append({"case": case, "ok": ok, **extra})
        if not ok:
            report["ok"] = False
        mark = "PASS" if ok else "FAIL"
        print(f"[{mark}] {case}" + (f" — {extra.get('detail','')}" if extra.get("detail") else ""))

    # P0
    assert "hunyuan-video" not in COMFYUI_PROVIDER_MAP
    assert "hunyuan-video-1.5" not in COMFYUI_PROVIDER_MAP
    record("P0 hunyuan removed from registry", True)

    with httpx.Client(timeout=60.0) as client:
        user, password = load_credentials()
        token = login(user, password)
        r = client.get(f"{BASE}/api/models", headers=headers(token), params={"category": "video"})
        r.raise_for_status()
        ids = {m["id"] for m in r.json().get("models", [])}
        record("P0 hunyuan-video not in user list", "hunyuan-video" not in ids)
        record("P0 ltx2-fp4 in user list", "ltx2-fp4" in ids)
        record("P0 hunyuan-video-1.5 not in user list", "hunyuan-video-1.5" not in ids)

        # P1 structure
        t2v = build_ltx2_fp4_t2v_workflow(PROMPT, NEG, width=854, height=480, duration_sec=5, audio=True)
        i2v = build_ltx2_fp4_i2v_workflow(
            PROMPT, NEG, image_filename="probe_ref.png", width=854, height=480, duration_sec=5, audio=False
        )
        t2v_types = {n.get("class_type") for n in t2v.values()}
        i2v_types = {n.get("class_type") for n in i2v.values()}
        record("P1 T2V workflow structure", "LTXAVTextEncoderLoader" in t2v_types, nodes=len(t2v))
        img2v_count = sum(1 for n in i2v.values() if n.get("class_type") == "LTXVImgToVideoInplace")
        record(
            "P1 I2V workflow structure",
            "LoadImage" in i2v_types and img2v_count >= 2,
            img2v_nodes=img2v_count,
        )
        t2v_silent = build_ltx2_fp4_t2v_workflow(PROMPT, NEG, width=854, height=480, duration_sec=5, audio=False)
        has_audio_nodes = any("Audio" in (n.get("class_type") or "") for n in t2v.values())
        silent_no_audio = not any("Audio" in (n.get("class_type") or "") for n in t2v_silent.values())
        record("P1 audio on has audio branch", has_audio_nodes)
        record("P1 audio off strips branch", silent_no_audio)

        # P1 FLF2V routing (submit only, check model rewrite via trace in generation_params after queue)
        flf = post_video(
            client,
            token,
            model="ltx2-fp4",
            generation_mode="keyframe",
            first_frame=FLF_FIRST,
            last_frame=FLF_LAST,
        )
        flf_ok = flf["status_code"] == 200 and flf["body"].get("task_id")
        record("P1 FLF2V submit accepts", flf_ok, status=flf["status_code"])
        if flf_ok:
            tid = flf["body"]["task_id"]
            routed_model = task_model_id_from_db(tid)
            record(
                "P1 FLF2V reroutes model",
                routed_model == "wan-i2v",
                model_id=routed_model,
            )

        # P1 real LTX2 T2V
        t0 = time.time()
        r = post_video(client, token, audio=False)
        if r["status_code"] != 200:
            record("P1 LTX2 T2V real", False, detail=r["body"])
        else:
            tid = r["body"]["task_id"]
            print(f"  … polling LTX2 T2V task {tid}")
            result = poll_task(client, token, tid, timeout=900)
            elapsed = round(time.time() - t0, 1)
            report["timings"]["ltx2_t2v_sec"] = elapsed
            record(
                "P1 LTX2 T2V real",
                result.get("status") == "completed" and bool(result.get("result")),
                elapsed_sec=elapsed,
                error=result.get("error"),
            )

        # Ref image for I2V via flux-dev
        t0 = time.time()
        ri = client.post(
            f"{BASE}/api/tasks/image",
            headers=headers(token),
            json={
                "model": "flux-dev",
                "prompt": "portrait photo of a woman on a beach at sunset, cinematic",
                "ratio": "16:9",
                "quality": "720P",
                "count": 1,
                "node_id": "probe-ref-image",
            },
            timeout=60,
        )
        ref_url = None
        if ri.status_code == 200:
            ref_tid = ri.json().get("task_id") or (ri.json().get("task_ids") or [None])[0]
            ref_res = poll_task(client, token, ref_tid, timeout=300)
            ref_url = ref_res.get("result")
            report["timings"]["flux_ref_sec"] = round(time.time() - t0, 1)
            record("P1 ref image for I2V", ref_res.get("status") == "completed", url=(ref_url or "")[:80])
        else:
            record("P1 ref image for I2V", False, detail=ri.text[:200])

        if ref_url:
            t0 = time.time()
            iv = post_video(
                client,
                token,
                generation_mode="freeref",
                reference_image=ref_url,
                audio=False,
            )
            if iv["status_code"] != 200:
                record("P1 LTX2 I2V real", False, detail=iv["body"])
            else:
                tid = iv["body"]["task_id"]
                print(f"  … polling LTX2 I2V task {tid}")
                result = poll_task(client, token, tid, timeout=900)
                elapsed = round(time.time() - t0, 1)
                report["timings"]["ltx2_i2v_sec"] = elapsed
                record(
                    "P1 LTX2 I2V real",
                    result.get("status") == "completed",
                    elapsed_sec=elapsed,
                    error=result.get("error"),
                )

        # Compare Wan T2V timing (same prompt/settings)
        t0 = time.time()
        wr = client.post(
            f"{BASE}/api/tasks/video",
            headers=headers(token),
            json={
                "model": "wan-2.6",
                "prompt": PROMPT,
                "negative_prompt": NEG,
                "ratio": "16:9",
                "resolution": "480P",
                "duration": 5,
                "node_id": "probe-wan-compare",
            },
            timeout=120,
        )
        if wr.status_code == 200:
            tid = wr.json().get("task_id")
            print(f"  … polling Wan compare task {tid}")
            result = poll_task(client, token, tid, timeout=600)
            report["timings"]["wan_t2v_sec"] = round(time.time() - t0, 1)
            record(
                "P1 Wan T2V compare",
                result.get("status") == "completed",
                elapsed_sec=report["timings"]["wan_t2v_sec"],
            )
        else:
            record("P1 Wan T2V compare", False, detail=wr.text[:200])

        # P2 flux-pulid structure via ComfyUI /prompt (workflow JSON, no providers import)
        pulid_wf = load_pulid_workflow_template()
        pr = httpx.post(
            f"{comfyui_http_url().rstrip('/')}/prompt",
            json={"prompt": pulid_wf},
            timeout=30,
        )
        record("P2 flux-pulid ComfyUI structure", pr.status_code == 200, status=pr.status_code)

        # P3 image enhance structure
        img_wf = build_seedvr2_image_enhance_workflow("probe.png", upscale_factor=2.0)
        ir = httpx.post(
            f"{comfyui_http_url().rstrip('/')}/prompt",
            json={"prompt": img_wf},
            timeout=30,
        )
        record("P3 SeedVR2 image structure", ir.status_code == 200)
        pulid_enabled = bool(COMFYUI_PROVIDER_MAP.get("flux-pulid", {}).get("enabled"))
        seedvr2_enabled = bool(
            COMFYUI_PROVIDER_MAP.get(IMAGE_ENHANCE_SEEDVR2_ID, {}).get("enabled")
        )
        record("P2 flux-pulid registry enabled", pulid_enabled)
        record("P3 image-enhance registry enabled", seedvr2_enabled)

        # P4 generation memory API
        proj = client.post(
            f"{BASE}/api/canvas/projects",
            headers=headers(token),
            json={"name": "probe-gen-memory"},
            timeout=30,
        )
        if proj.status_code == 200:
            pid = proj.json().get("id")
            gm = client.put(
                f"{BASE}/api/projects/{pid}/generation-memory",
                headers=headers(token),
                json={
                    "protagonist_face_url": "/uploads/probe/face.png",
                    "preferred_video_model": "ltx2-fp4",
                },
                timeout=30,
            )
            record("P4 generation-memory PUT", gm.status_code == 200)
            gr = client.get(
                f"{BASE}/api/projects/{pid}/generation-memory",
                headers=headers(token),
                timeout=30,
            )
            mem = gr.json().get("generation_memory", {}) if gr.status_code == 200 else {}
            record(
                "P4 generation-memory GET",
                mem.get("preferred_video_model") == "ltx2-fp4",
                face=mem.get("protagonist_face_url"),
            )
        else:
            record("P4 generation-memory", False, detail=proj.text[:200])

    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"\nReport: {OUT}")
    print(f"Overall: {'PASS' if report['ok'] else 'FAIL'}")
    return 0 if report["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
