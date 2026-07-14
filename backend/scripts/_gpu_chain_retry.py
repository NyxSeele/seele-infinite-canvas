#!/usr/bin/env python3
"""Retry Wan + Agent after chain probe partial failure."""
from __future__ import annotations

import json
import sys
import time
import uuid
from pathlib import Path

import httpx

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
sys.path.insert(0, str(Path(__file__).resolve().parent))

from _agent_pipeline_e2e_probe import BASE, headers, login

OUT = Path("/root/autodl-tmp/logs/gpu_chain_retry.json")


def poll(client, token, tid, timeout=900):
    dead = time.time() + timeout
    last = {}
    while time.time() < dead:
        r = client.get(f"{BASE}/api/tasks/{tid}", headers=headers(token), timeout=30)
        r.raise_for_status()
        last = r.json()
        st = last.get("status")
        print(f"  poll {tid[:8]} status={st}", flush=True)
        if st in ("completed", "failed"):
            return last
        time.sleep(5)
    raise TimeoutError(last)


def main() -> int:
    out = {"ok": True, "steps": []}
    with httpx.Client(timeout=60) as client:
        token = login("admin", "Admin@2026!")

        # Prefer existing running wan task if any
        from db.session import SessionLocal
        from models import Task

        db = SessionLocal()
        running = (
            db.query(Task)
            .filter(Task.task_type == "video", Task.status.in_(("pending", "running", "queued")))
            .order_by(Task.created_at.desc())
            .first()
        )
        db.close()

        t0 = time.time()
        if running:
            print(f"reuse running video task {running.id}", flush=True)
            tid = running.id
        else:
            r = client.post(
                f"{BASE}/api/tasks/video",
                headers=headers(token),
                json={
                    "model": "wan-2.6",
                    "prompt": "chain probe: a woman walking in rain, cinematic neon",
                    "ratio": "16:9",
                    "duration": 3,
                    "resolution": "720P",
                    "node_id": f"chain-wan-{uuid.uuid4().hex[:8]}",
                    "sampling_profile": "fast",
                },
            )
            print("wan submit", r.status_code, r.text[:300], flush=True)
            if r.status_code >= 400:
                out["ok"] = False
                out["steps"].append({"check": "wan", "ok": False, "body": r.text[:400]})
                OUT.write_text(json.dumps(out, ensure_ascii=False, indent=2))
                return 3
            tid = r.json()["task_id"]

        task = poll(client, token, tid, 1200)
        ok = task.get("status") == "completed" and bool(task.get("result"))
        out["steps"].append(
            {
                "check": "wan",
                "ok": ok,
                "status": task.get("status"),
                "result": str(task.get("result") or "")[:120],
                "error": task.get("error"),
                "sec": round(time.time() - t0, 1),
            }
        )
        out["ok"] = out["ok"] and ok
        print("wan result", out["steps"][-1], flush=True)

        t0 = time.time()
        ar = client.post(
            f"{BASE}/api/agent/run",
            headers=headers(token),
            json={
                "project_id": str(uuid.uuid4()),
                "canvas_snapshot": {
                    "nodes": [],
                    "edges": [],
                    "selected_node_ids": [],
                    "total_node_count": 0,
                    "snapshot_truncated": False,
                    "omitted_node_count": 0,
                },
                "messages": [
                    {
                        "role": "user",
                        "content": "雨夜重庆，一个女人独自等待，请先给出创意方向卡片，3个镜头",
                    }
                ],
                "execution_mode": "manual",
            },
            timeout=180,
        )
        events = []
        for line in ar.text.splitlines():
            if line.startswith("data: "):
                try:
                    events.append(json.loads(line[6:]))
                except json.JSONDecodeError:
                    pass
        agent_ok = ar.status_code < 400 and (bool(events) or "actions" in ar.text)
        out["steps"].append(
            {
                "check": "agent",
                "ok": agent_ok,
                "http": ar.status_code,
                "events": len(events),
                "types": [e.get("type") or e.get("event") for e in events[:8]],
                "sample": str(events[:2])[:500],
                "sec": round(time.time() - t0, 1),
            }
        )
        out["ok"] = out["ok"] and agent_ok
        print("agent result", out["steps"][-1], flush=True)

    OUT.write_text(json.dumps(out, ensure_ascii=False, indent=2), encoding="utf-8")
    print("FINAL", out["ok"], flush=True)
    return 0 if out["ok"] else 3


if __name__ == "__main__":
    raise SystemExit(main())
