#!/usr/bin/env python3
"""Prompt 调试阶段四：HunyuanVideo T2V T1–T4（轻量 steps=10 / 544x320）。"""
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

OUT = Path("/root/autodl-tmp/logs/prompt_debug_phase4_hunyuan.json")
POLL_TIMEOUT = 3600  # 轻量仍可能较慢

CASES = [
    {
        "id": "T1",
        "prompt": "雨中街道，行人撑伞走过",
        "quality_preset_id": None,
        "note": "中文短句",
    },
    {
        "id": "T2",
        "prompt": "黄昏海边，浪花拍打礁石，镜头缓慢推进",
        "quality_preset_id": "cinematic",
        "note": "中文+cinematic",
    },
    {
        "id": "T3",
        "prompt": "a cat walking across a wooden floor in soft morning light",
        "quality_preset_id": None,
        "note": "英文",
    },
    {
        "id": "T4",
        "prompt": (
            "古老的江南水乡，青石板路被雨水打湿，远处有乌篷船缓缓划过，"
            "屋檐下挂着红灯笼，薄雾笼罩着白墙黑瓦，镜头从巷口缓缓推向河面"
        ),
        "quality_preset_id": "documentary",
        "note": "中文长描述+documentary",
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
        "l3_final": trace.get("l3_final_len"),
        "l4_steps": l4.get("steps") or l4.get("sample_steps"),
        "l4_size": f"{l4.get('width')}x{l4.get('height')}" if l4 else None,
        "l4_mode": l4.get("workflow_mode") or l4.get("backend"),
    }


async def run() -> dict:
    log_start = LOG_PATH.stat().st_size if LOG_PATH.is_file() else 0
    trace_ids = {c["id"]: str(uuid.uuid4()) for c in CASES}
    tasks_out: dict[str, dict] = {}

    async with httpx.AsyncClient(timeout=120.0) as client:
        token = await login_admin(client)
        headers = {"Authorization": f"Bearer {token}"}
        for case in CASES:
            tid = trace_ids[case["id"]]
            body = {
                "model": "hunyuan-video",
                "prompt": case["prompt"],
                "generation_mode": "keyframe",
                "ratio": "16:9",
                "resolution": "720P",
                "duration": 5,
                "audio": False,
                "count": 1,
                "node_id": f"probe-p4-{case['id']}",
                "trace_id": tid,
                "steps": 10,
                "width": 544,
                "height": 320,
            }
            if case.get("quality_preset_id"):
                body["quality_preset_id"] = case["quality_preset_id"]
            print(f"=== {case['id']} submit ===", flush=True)
            r = await client.post(f"{BASE}/api/tasks/video", headers=headers, json=body)
            if r.status_code >= 400:
                tasks_out[case["id"]] = {
                    "status": "submit_failed",
                    "error": r.text[:500],
                    "http_status": r.status_code,
                }
                print(f"  submit fail {r.status_code}: {r.text[:200]}", flush=True)
                continue
            task_id = r.json()["task_id"]
            tasks_out[case["id"]] = await poll_task(client, token, task_id)

    traces = parse_traces_from_log(trace_ids, log_start)
    tables = [
        build_table(c["id"], traces.get(c["id"], {}), c, tasks_out.get(c["id"], {}))
        for c in CASES
    ]
    payload = {
        "label": "phase4_hunyuan_light",
        "overrides": {"steps": 10, "width": 544, "height": 320},
        "cases": {c["id"]: {"prompt": c["prompt"], "task": tasks_out.get(c["id"])} for c in CASES},
        "tables": tables,
        "trace_ids": trace_ids,
    }
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps({"tables": tables}, ensure_ascii=False, indent=2))
    return payload


if __name__ == "__main__":
    # monkey-patch longer timeout for hunyuan light
    import _prompt_debug_phase2 as p2

    p2.POLL_TIMEOUT = POLL_TIMEOUT
    asyncio.run(run())
