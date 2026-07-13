#!/usr/bin/env python3
"""Prompt 调试阶段一：Flux 单卡 T1–T4 + SSE trace 采集。"""
from __future__ import annotations

import asyncio
import json
import sys
import time
import uuid
from pathlib import Path

import httpx

BASE = "http://127.0.0.1:7788"
POLL_INTERVAL = 2
POLL_TIMEOUT = 300


def load_password() -> str:
    env_path = Path(__file__).resolve().parents[1] / ".env"
    for line in env_path.read_text().splitlines():
        if line.startswith("SEED_TESTUSER_PASSWORD="):
            return line.split("=", 1)[1].strip()
    raise RuntimeError("SEED_TESTUSER_PASSWORD not found")


def summarize(text: str | None, n: int = 120) -> str:
    if not text:
        return ""
    s = " ".join(str(text).split())
    return s if len(s) <= n else s[: n - 1] + "…"


CASES = [
    {
        "id": "T1",
        "label": "中文无 preset",
        "body": {
            "model": "flux-dev",
            "prompt": "一个女人站在雨中的胡同里",
            "ratio": "1:1",
            "quality": "2K",
            "count": 1,
            "node_id": "prompt-debug-t1",
        },
    },
    {
        "id": "T2",
        "label": "中文 + cinematic preset",
        "body": {
            "model": "flux-dev",
            "prompt": "一个女人站在雨中的胡同里",
            "quality_preset_id": "cinematic",
            "ratio": "1:1",
            "quality": "2K",
            "count": 1,
            "node_id": "prompt-debug-t2",
        },
    },
    {
        "id": "T3",
        "label": "英文对照",
        "body": {
            "model": "flux-dev",
            "prompt": "a woman standing in a rain-soaked alley, photorealistic",
            "ratio": "1:1",
            "quality": "2K",
            "count": 1,
            "node_id": "prompt-debug-t3",
        },
    },
    {
        "id": "T4",
        "label": "中文 + 角色描述（prompt 内联，API 无 character_refs）",
        "body": {
            "model": "flux-dev",
            "prompt": "林晓，长直黑发，白色风衣，东亚面孔，25岁。一个女人站在雨中的胡同里",
            "ratio": "1:1",
            "quality": "2K",
            "count": 1,
            "node_id": "prompt-debug-t4",
        },
    },
]


async def login(client: httpx.AsyncClient) -> str:
    r = await client.post(
        f"{BASE}/api/auth/login",
        json={"username_or_email": "testuser", "password": load_password()},
    )
    r.raise_for_status()
    return r.json()["access_token"]


async def poll_task(client: httpx.AsyncClient, token: str, task_id: str) -> dict:
    headers = {"Authorization": f"Bearer {token}"}
    deadline = time.time() + POLL_TIMEOUT
    while time.time() < deadline:
        r = await client.get(f"{BASE}/api/tasks/{task_id}", headers=headers)
        r.raise_for_status()
        data = r.json()
        if data.get("status") in ("completed", "failed"):
            return data
        await asyncio.sleep(POLL_INTERVAL)
    raise TimeoutError(f"task {task_id} timeout")


async def trace_collector(
    trace_ids: set[str],
    store: dict[str, dict[int, dict]],
    stop: asyncio.Event,
) -> None:
    async with httpx.AsyncClient(timeout=None) as client:
        try:
            async with client.stream("GET", f"{BASE}/api/debug/trace/stream") as resp:
                resp.raise_for_status()
                async for line in resp.aiter_lines():
                    if stop.is_set():
                        return
                    if not line.startswith("data: "):
                        continue
                    try:
                        msg = json.loads(line[6:])
                    except json.JSONDecodeError:
                        continue
                    tid = (msg.get("data") or {}).get("trace_id")
                    if tid not in trace_ids:
                        continue
                    layer = msg.get("layer")
                    if layer is not None:
                        store.setdefault(tid, {})[int(layer)] = msg
        except Exception as exc:
            store["_collector_error"] = {"error": str(exc)}


def build_table(case_id: str, trace_id: str, layers: dict[int, dict]) -> list[dict]:
    rows = []
    l1 = layers.get(1, {}).get("data") or {}
    l2 = layers.get(2, {}).get("data") or {}
    l3 = layers.get(3, {}).get("data") or {}
    l4 = layers.get(4, {}).get("data") or {}

    rows.append({"case": case_id, "layer": "L1", "tag": "SUBMIT", "summary": summarize(l1.get("prompt"))})
    rows.append({"case": case_id, "layer": "L2", "tag": "RECEIVED", "summary": summarize(l2.get("prompt"))})
    rows.append({"case": case_id, "layer": "L3", "tag": "before", "summary": summarize(l3.get("before"))})
    rows.append({"case": case_id, "layer": "L3", "tag": "after", "summary": summarize(l3.get("after"))})
    rows.append({
        "case": case_id,
        "layer": "L4",
        "tag": "positive",
        "summary": summarize(l4.get("positive_prompt")),
    })
    steps = l4.get("steps")
    cfg = l4.get("cfg")
    rows.append({
        "case": case_id,
        "layer": "L4",
        "tag": "steps/cfg",
        "summary": f"steps={steps} cfg/guidance={cfg} size={l4.get('width')}x{l4.get('height')}",
    })
    return rows


async def run_phase(label: str) -> dict:
    trace_ids: dict[str, str] = {}
    for c in CASES:
        trace_ids[c["id"]] = str(uuid.uuid4())

    store: dict[str, dict[int, dict]] = {}
    stop = asyncio.Event()
    collector_task = asyncio.create_task(
        trace_collector(set(trace_ids.values()), store, stop)
    )
    await asyncio.sleep(0.5)

    results: dict = {"label": label, "cases": {}, "tables": []}

    async with httpx.AsyncClient(timeout=120.0) as client:
        token = await login(client)
        headers = {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}

        for case in CASES:
            cid = case["id"]
            tid = trace_ids[cid]
            body = {**case["body"], "trace_id": tid}
            print(f"\n[{label}] {cid} submit trace_id={tid[:8]}…", flush=True)
            r = await client.post(f"{BASE}/api/tasks/image", headers=headers, json=body)
            if r.status_code >= 400:
                results["cases"][cid] = {"error": r.text, "status": r.status_code}
                continue
            task_id = r.json().get("task_id") or (r.json().get("task_ids") or [None])[0]
            task = await poll_task(client, token, task_id)
            results["cases"][cid] = {
                "task_id": task_id,
                "status": task.get("status"),
                "error": task.get("error"),
                "trace_id": tid,
            }
            print(f"  → {task.get('status')} task_id={task_id}", flush=True)

    await asyncio.sleep(1)
    stop.set()
    collector_task.cancel()
    try:
        await collector_task
    except asyncio.CancelledError:
        pass

    for case in CASES:
        cid = case["id"]
        tid = trace_ids[cid]
        layers = store.get(tid, {})
        results["tables"].extend(build_table(cid, tid, layers))
        results["cases"].setdefault(cid, {})["layers"] = layers

    return results


def main() -> int:
    label = sys.argv[1] if len(sys.argv) > 1 else "baseline"
    out_path = Path(f"/root/autodl-tmp/logs/prompt_debug_phase1_{label}.json")
    data = asyncio.run(run_phase(label))
    out_path.write_text(json.dumps(data, ensure_ascii=False, indent=2))
    print(f"\nWrote {out_path}")
    for row in data["tables"]:
        print(f"{row['case']} {row['layer']} {row['tag']}: {row['summary']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
