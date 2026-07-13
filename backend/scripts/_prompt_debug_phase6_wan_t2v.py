#!/usr/bin/env python3
"""Prompt 调试阶段六：Wan T2V T1–T4。"""
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
)

OUT = Path("/root/autodl-tmp/logs/prompt_debug_phase6_wan_t2v.json")
POLL_TIMEOUT = 1800

CASES = [
    {
        "id": "T1",
        "prompt": "城市天桥上行人匆匆走过",
        "sampling_profile": "fast",
        "camera_move": "auto",
        "shot_scale": "auto",
        "quality_preset_id": None,
        "sound_note": None,
        "note": "fast 4步",
    },
    {
        "id": "T2",
        "prompt": "镜头缓缓推进，女孩抬头望向天空",
        "sampling_profile": "quality",
        "camera_move": "push_in",
        "shot_scale": "medium",
        "quality_preset_id": "cinematic",
        "sound_note": None,
        "note": "push_in+quality",
    },
    {
        "id": "T3",
        "prompt": "camera slowly pans across a quiet library aisle",
        "sampling_profile": "quality",
        "camera_move": "pan",
        "shot_scale": "wide",
        "quality_preset_id": None,
        "sound_note": None,
        "note": "英文运镜",
    },
    {
        "id": "T4",
        "prompt": "广阔草原上马群奔驰，尘土飞扬",
        "sampling_profile": "quality",
        "camera_move": "track",
        "shot_scale": "wide",
        "quality_preset_id": "documentary",
        "sound_note": "马蹄与风声",
        "note": "wide+sound_note",
    },
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


def build_table(cid: str, trace: dict, case: dict, task: dict) -> dict:
    l4 = trace.get("l4") or {}
    return {
        "id": cid,
        "note": case.get("note"),
        "status": task.get("status"),
        "error": task.get("error"),
        "result": summarize(task.get("result"), 80),
        "l2_prompt_len": trace.get("l2_prompt_len"),
        "l3_before": trace.get("l3_before_len"),
        "l3_after": trace.get("l3_after_len"),
        "l4_steps": l4.get("steps"),
        "l4_mode": l4.get("workflow_mode") or l4.get("backend"),
    }


async def run() -> dict:
    import _prompt_debug_phase2 as p2

    p2.POLL_TIMEOUT = POLL_TIMEOUT
    log_start = LOG_PATH.stat().st_size if LOG_PATH.is_file() else 0
    trace_ids = {c["id"]: str(uuid.uuid4()) for c in CASES}
    tasks_out: dict[str, dict] = {}

    async with httpx.AsyncClient(timeout=120.0) as client:
        token = await login_admin(client)
        headers = {"Authorization": f"Bearer {token}"}
        for case in CASES:
            tid = trace_ids[case["id"]]
            body = {
                "model": "wan-2.6",
                "prompt": case["prompt"],
                "generation_mode": "keyframe",
                "ratio": "16:9",
                "resolution": "720P",
                "duration": 5,
                "audio": False,
                "count": 1,
                "node_id": f"probe-p6-{case['id']}",
                "trace_id": tid,
                "sampling_profile": case["sampling_profile"],
                "camera_move": case["camera_move"],
                "shot_scale": case["shot_scale"],
            }
            if case.get("quality_preset_id"):
                body["quality_preset_id"] = case["quality_preset_id"]
            if case.get("sound_note"):
                body["sound_note"] = case["sound_note"]
            print(f"=== {case['id']} {case['note']} ===", flush=True)
            r = await client.post(f"{BASE}/api/tasks/video", headers=headers, json=body)
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
        for c in CASES
    ]
    payload = {
        "label": "phase6_wan_t2v",
        "cases": {c["id"]: {"prompt": c["prompt"], "task": tasks_out.get(c["id"])} for c in CASES},
        "tables": tables,
        "trace_ids": trace_ids,
    }
    OUT.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps({"tables": tables}, ensure_ascii=False, indent=2))
    return payload


if __name__ == "__main__":
    asyncio.run(run())
