#!/usr/bin/env python3
"""Prompt 调试阶段三：首尾帧 FLF2V K1–K4 + backend.out.log trace 解析。"""
from __future__ import annotations

import asyncio
import json
import sys
import uuid
from pathlib import Path

import httpx

# 复用 phase2 工具
sys.path.insert(0, str(Path(__file__).resolve().parent))
from _prompt_debug_phase2 import (  # noqa: E402
    BASE,
    LOG_PATH,
    POLL_INTERVAL,
    POLL_TIMEOUT,
    PROMPT_ZH,
    build_table,
    load_password,
    login,
    parse_traces_from_log,
    poll_task,
    upload_image_file,
    upload_view_url_as_uploads,
)

PROMPT_FLUX_A = "a woman standing in a rain-soaked hutong, photorealistic, cinematic"
PROMPT_FLUX_B = (
    "the same woman walking away down a rain-soaked hutong alley, photorealistic, cinematic"
)

CASES = [
    {
        "id": "K1",
        "prompt": PROMPT_ZH,
        "first_key": "A",
        "last_key": "B",
        "quality_preset_id": "cinematic",
    },
    {
        "id": "K2",
        "prompt": PROMPT_ZH,
        "first_key": "A",
        "last_key": "B_upload",
        "quality_preset_id": "cinematic",
    },
    {
        "id": "K3",
        "prompt": PROMPT_ZH,
        "first_key": "A",
        "last_key": None,
        "quality_preset_id": "cinematic",
    },
    {
        "id": "K4",
        "prompt": PROMPT_ZH,
        "first_key": "A",
        "last_key": "A",
        "quality_preset_id": "cinematic",
    },
]


async def flux_ref(client: httpx.AsyncClient, token: str, prompt: str, node_suffix: str) -> str:
    headers = {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}
    r = await client.post(
        f"{BASE}/api/tasks/image",
        headers=headers,
        json={
            "model": "flux-dev",
            "prompt": prompt,
            "quality_preset_id": "cinematic",
            "ratio": "16:9",
            "quality": "2K",
            "count": 1,
            "node_id": f"phase3-flux-{node_suffix}",
            "trace_id": str(uuid.uuid4()),
        },
        timeout=120,
    )
    r.raise_for_status()
    task_id = r.json().get("task_id") or (r.json().get("task_ids") or [None])[0]
    print(f"[prep] flux {node_suffix} task {task_id}", flush=True)
    img = await poll_task(client, token, task_id)
    if img.get("status") != "completed":
        raise RuntimeError(f"flux {node_suffix} failed: {img.get('error')}")
    url = img.get("result")
    if not url:
        raise RuntimeError(f"flux {node_suffix} missing result")
    return url


async def prepare_frames(client: httpx.AsyncClient, token: str) -> dict[str, str]:
    url_a = await flux_ref(client, token, PROMPT_FLUX_A, "a")
    url_b = await flux_ref(client, token, PROMPT_FLUX_B, "b")
    cache_b = Path("/tmp/phase3_flux_ref_b.png")
    url_b_upload = await upload_view_url_as_uploads(client, token, url_b, cache_b)
    print(f"[prep] ref A={url_a[:60]}…", flush=True)
    print(f"[prep] ref B view={url_b[:60]}…", flush=True)
    print(f"[prep] ref B upload={url_b_upload[:60]}…", flush=True)
    return {"A": url_a, "B": url_b, "B_upload": url_b_upload}


def main() -> int:
    only_case = sys.argv[1].upper() if len(sys.argv) > 1 else None
    cases = CASES
    if only_case:
        cases = [c for c in CASES if c["id"] == only_case]
        if not cases:
            print(f"Unknown case {only_case!r}, expected one of: K1 K2 K3 K4", file=sys.stderr)
            return 2

    out = Path(f"/root/autodl-tmp/logs/prompt_debug_phase3_{only_case.lower() if only_case else 'keyframe'}.json")

    async def _run() -> dict:
        log_start = LOG_PATH.stat().st_size if LOG_PATH.is_file() else 0
        trace_ids = {c["id"]: str(uuid.uuid4()) for c in cases}
        results: dict = {
            "label": f"phase3-{only_case.lower()}" if only_case else "phase3-keyframe",
            "cases": {},
            "tables": [],
        }
        async with httpx.AsyncClient(timeout=180.0) as client:
            token = await login(client)
            refs = await prepare_frames(client, token)
            headers = {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}
            for case in cases:
                cid = case["id"]
                tid = trace_ids[cid]
                body = {
                    "model": "wan-i2v",
                    "prompt": case["prompt"],
                    "ratio": "16:9",
                    "resolution": "720P",
                    "duration": 3,
                    "count": 1,
                    "node_id": f"prompt-debug-{cid.lower()}",
                    "trace_id": tid,
                    "generation_mode": "keyframe",
                    "first_frame": refs[case["first_key"]],
                }
                if case.get("quality_preset_id"):
                    body["quality_preset_id"] = case["quality_preset_id"]
                if case.get("last_key"):
                    body["last_frame"] = refs[case["last_key"]]
                print(f"\n[phase3] {cid} submit trace_id={tid[:8]}…", flush=True)
                r = await client.post(f"{BASE}/api/tasks/video", headers=headers, json=body)
                if r.status_code >= 400:
                    results["cases"][cid] = {"error": r.text, "status_code": r.status_code}
                    continue
                task_id = r.json().get("task_id") or (r.json().get("task_ids") or [None])[0]
                task = await poll_task(client, token, task_id)
                results["cases"][cid] = {
                    "task_id": task_id,
                    "status": task.get("status"),
                    "error": task.get("error"),
                    "result": task.get("result"),
                    "trace_id": tid,
                }
        traces = parse_traces_from_log(trace_ids, log_start)
        for case in cases:
            cid = case["id"]
            trace = traces.get(cid, {})
            task = results["cases"].get(cid, {})
            results["cases"].setdefault(cid, {})["trace"] = trace
            l4 = trace.get("l4") or {}
            if l4:
                task.setdefault("workflow_mode", l4.get("workflow_mode"))
            results["tables"].extend(build_table(cid, trace, case, task))
        return results

    data = asyncio.run(_run())
    out.write_text(json.dumps(data, ensure_ascii=False, indent=2))
    print(f"\nWrote {out}")
    for row in data["tables"]:
        print(f"{row['case']} {row['layer']} {row['tag']}: {row['summary']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
