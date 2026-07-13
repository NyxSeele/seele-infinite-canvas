#!/usr/bin/env python3
"""Prompt 调试阶段七：flux-pulid 有/无参考图。"""
from __future__ import annotations

import asyncio
import json
import sys
import uuid
from pathlib import Path

import httpx

BACKEND_ROOT = Path(__file__).resolve().parents[1]
SCRIPTS_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(SCRIPTS_DIR))
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

from _prompt_debug_phase2 import (  # noqa: E402
    BASE,
    LOG_PATH,
    parse_traces_from_log,
    poll_task,
    summarize,
    upload_image_file,
)

OUT = Path("/root/autodl-tmp/logs/prompt_debug_phase7_pulid.json")
POLL_TIMEOUT = 900
FACE_CANDIDATES = [
    Path("/root/autodl-tmp/ComfyUI/input"),
    Path("/root/autodl-tmp/AIStudio/backend/uploads/images"),
    Path("/root/autodl-tmp/ComfyUI/output"),
]


def load_admin_password() -> str:
    env_path = BACKEND_ROOT / ".env"
    for line in env_path.read_text().splitlines():
        if line.startswith("SEED_ADMIN_PASSWORD="):
            return line.split("=", 1)[1].strip()
    raise RuntimeError("SEED_ADMIN_PASSWORD not found")


async def login_admin(client: httpx.AsyncClient) -> str:
    r = await client.post(
        f"{BASE}/api/auth/login",
        json={"username_or_email": "admin", "password": load_admin_password()},
    )
    r.raise_for_status()
    return r.json()["access_token"]


def find_local_face() -> Path | None:
    for root in FACE_CANDIDATES:
        if not root.is_dir():
            continue
        for p in sorted(root.rglob("*")):
            if p.suffix.lower() in (".png", ".jpg", ".jpeg", ".webp") and p.is_file():
                if p.stat().st_size > 10_000:
                    return p
    return None


def build_table(cid: str, trace: dict, case: dict, task: dict) -> dict:
    l4 = trace.get("l4") or {}
    return {
        "id": cid,
        "note": case.get("note"),
        "status": task.get("status"),
        "http_status": task.get("http_status"),
        "error": summarize(task.get("error"), 120),
        "result": summarize(task.get("result"), 80),
        "l2_prompt_len": trace.get("l2_prompt_len"),
        "l3_before": trace.get("l3_before_len"),
        "l3_after": trace.get("l3_after_len"),
        "l4_mode": l4.get("workflow_mode"),
        "l4_use_reactor": l4.get("use_reactor") or ("reactor" in str(l4.get("workflow_mode", "")).lower()),
    }


async def run() -> dict:
    import _prompt_debug_phase2 as p2

    p2.POLL_TIMEOUT = POLL_TIMEOUT
    log_start = LOG_PATH.stat().st_size if LOG_PATH.is_file() else 0
    face = find_local_face()
    cases_meta = [
        {"id": "T1", "note": "无参考图（预期失败）", "ref": None, "preset": None, "neg": None},
        {"id": "T2", "note": "有参考图 uploads", "ref": "uploads", "preset": "cinematic", "neg": "blurry, low quality"},
        {"id": "T3", "note": "有参考图 uploads EN", "ref": "uploads", "preset": None, "neg": None, "prompt_en": True},
        {"id": "T4", "note": "非法参考图 URL", "ref": "illegal", "preset": None, "neg": "worst quality"},
    ]
    trace_ids = {c["id"]: str(uuid.uuid4()) for c in cases_meta}
    tasks_out: dict[str, dict] = {}

    async with httpx.AsyncClient(timeout=120.0) as client:
        token = await login_admin(client)
        headers = {"Authorization": f"Bearer {token}"}
        uploads_url = None
        if face:
            uploads_url = await upload_image_file(client, token, face, filename=f"p7_face{face.suffix}")
            print(f"face upload={uploads_url} from {face}", flush=True)
        else:
            print("WARNING: no local face image found", flush=True)

        for case in cases_meta:
            tid = trace_ids[case["id"]]
            prompt = (
                "a portrait of a young woman looking at the camera, soft light"
                if case.get("prompt_en")
                else "一位年轻女性正面肖像，柔和光线"
            )
            body = {
                "model": "flux-pulid",
                "prompt": prompt,
                "quality": "2K",
                "ratio": "1:1",
                "count": 1,
                "node_id": f"probe-p7-{case['id']}",
                "trace_id": tid,
                # G40 ReActor 需 buffalo_l；本机缺权重且外网不可达时默认关，仅验 PuLID 链路
                "use_reactor": False,
            }
            if case.get("preset"):
                body["quality_preset_id"] = case["preset"]
            if case.get("neg"):
                body["negative_prompt"] = case["neg"]
            if case["ref"] == "uploads":
                if not uploads_url:
                    tasks_out[case["id"]] = {
                        "status": "skipped",
                        "error": "no face image available",
                    }
                    continue
                body["reference_image"] = uploads_url
                body["reference_images"] = [uploads_url]
            elif case["ref"] == "illegal":
                body["reference_image"] = "/api/uploads/images/__no_such_face_g40__.png"
                body["reference_images"] = [body["reference_image"]]
            # T1: no reference

            print(f"=== {case['id']} {case['note']} ===", flush=True)
            r = await client.post(f"{BASE}/api/tasks/image", headers=headers, json=body)
            if r.status_code >= 400:
                tasks_out[case["id"]] = {
                    "status": "submit_failed",
                    "error": r.text[:500],
                    "http_status": r.status_code,
                }
                continue
            tasks_out[case["id"]] = await poll_task(client, token, r.json()["task_id"])

    traces = parse_traces_from_log(trace_ids, log_start)
    tables = [
        build_table(c["id"], traces.get(c["id"], {}), c, tasks_out.get(c["id"], {}))
        for c in cases_meta
    ]
    payload = {
        "label": "phase7_pulid",
        "face_source": str(face) if face else None,
        "cases": {c["id"]: {"note": c["note"], "task": tasks_out.get(c["id"])} for c in cases_meta},
        "tables": tables,
        "trace_ids": trace_ids,
    }
    OUT.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps({"tables": tables}, ensure_ascii=False, indent=2))
    return payload


if __name__ == "__main__":
    asyncio.run(run())
