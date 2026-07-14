#!/usr/bin/env python3
"""双 GPU 快速冒烟：基础设施 + GPUPool + 并发 wan-2.6 T2V。"""
from __future__ import annotations

import json
import os
import sqlite3
import subprocess
import sys
import threading
import time
import uuid
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone
from pathlib import Path

import httpx

BACKEND_ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = Path(__file__).resolve().parent
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))

from _agent_pipeline_e2e_probe import BASE, headers, login  # noqa: E402
from core.comfyui_settings import comfyui_nodes_list  # noqa: E402
from services.gpu_pool import GPUPool, reset_gpu_pool_for_tests  # noqa: E402

OUT = Path("/root/autodl-tmp/logs/dual_gpu_smoke.json")
DB_PATH = BACKEND_ROOT / "aistudio.db"
SUPERVISORCTL = "/usr/bin/supervisorctl"
SUPERVISOR_CONF = "/etc/supervisor/supervisord.conf"
COMFY_PORTS = ("8000", "8001")
POLL_INTERVAL = 3.0
POLL_TIMEOUT = 180.0
NVIDIA_SAMPLE_INTERVAL = 5.0
NVIDIA_SAMPLE_COUNT = 3
UTIL_THRESHOLD = 5

WAN_PAYLOAD = {
    "model": "wan-2.6",
    "prompt": "dual gpu smoke: static red cube on table",
    "ratio": "16:9",
    "resolution": "480P",
    "duration": 5,
    "sampling_profile": "fast",
    "generation_mode": "keyframe",
    "count": 1,
    "audio": False,
}


def load_admin_password() -> str:
    env_path = BACKEND_ROOT / ".env"
    if env_path.is_file():
        for line in env_path.read_text(encoding="utf-8").splitlines():
            if line.startswith("SEED_ADMIN_PASSWORD="):
                return line.split("=", 1)[1].strip().strip('"').strip("'")
    raise RuntimeError("SEED_ADMIN_PASSWORD not found in backend/.env")


def load_admin_username() -> str:
    return "seele"


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _supervisor_status(name: str) -> str:
    try:
        proc = subprocess.run(
            [SUPERVISORCTL, "-c", SUPERVISOR_CONF, "status", name],
            capture_output=True,
            text=True,
            timeout=10,
            check=False,
        )
        line = (proc.stdout or proc.stderr or "").strip()
        if "running" in line.lower():
            return "RUNNING"
        return line or "UNKNOWN"
    except Exception as exc:
        return f"ERROR:{exc}"


def _comfyui_pid(port: str) -> int | None:
    try:
        proc = subprocess.run(
            ["pgrep", "-f", f"ComfyUI/main.py --listen 127.0.0.1 --port {port}"],
            capture_output=True,
            text=True,
            timeout=5,
            check=False,
        )
        lines = [ln.strip() for ln in (proc.stdout or "").splitlines() if ln.strip()]
        if not lines:
            return None
        return int(lines[0])
    except Exception:
        return None


def _cuda_visible_devices(pid: int | None) -> str | None:
    if not pid:
        return None
    env_path = Path(f"/proc/{pid}/environ")
    if not env_path.is_file():
        return None
    try:
        raw = env_path.read_bytes()
        for item in raw.split(b"\0"):
            if item.startswith(b"CUDA_VISIBLE_DEVICES="):
                return item.decode("utf-8", errors="replace").split("=", 1)[1]
    except Exception:
        return None
    return None


def _comfyui_health(port: str) -> dict:
    url = f"http://127.0.0.1:{port}/system_stats"
    try:
        r = httpx.get(url, timeout=8)
        ok = r.status_code == 200
        devices = []
        if ok:
            data = r.json()
            devices = data.get("devices") or []
        return {
            "port": port,
            "ok": ok,
            "status_code": r.status_code,
            "device_count": len(devices),
        }
    except Exception as exc:
        return {"port": port, "ok": False, "error": str(exc)}


def _sample_nvidia() -> list[dict]:
    try:
        proc = subprocess.run(
            [
                "nvidia-smi",
                "--query-gpu=index,utilization.gpu,memory.used",
                "--format=csv,noheader,nounits",
            ],
            capture_output=True,
            text=True,
            timeout=10,
            check=False,
        )
        rows: list[dict] = []
        for line in (proc.stdout or "").strip().splitlines():
            parts = [p.strip() for p in line.split(",")]
            if len(parts) >= 3:
                rows.append(
                    {
                        "index": int(parts[0]),
                        "util_gpu": int(parts[1]),
                        "memory_used_mib": int(parts[2]),
                    }
                )
        return rows
    except Exception as exc:
        return [{"error": str(exc)}]


def _dual_gpu_util_seen(samples: list[dict]) -> bool:
    for sample in samples:
        rows = sample.get("gpus") or []
        if not rows or rows[0].get("error"):
            continue
        by_index = {r["index"]: r for r in rows if "index" in r}
        g0 = by_index.get(0, {}).get("util_gpu", 0)
        g1 = by_index.get(1, {}).get("util_gpu", 0)
        if g0 > UTIL_THRESHOLD and g1 > UTIL_THRESHOLD:
            return True
    return False


def phase0_preflight(report: dict) -> list[str]:
    issues: list[str] = []
    checks: dict = {}

    for name in ("aistudio-backend", "comfyui0", "comfyui1"):
        st = _supervisor_status(name)
        checks[f"supervisor_{name}"] = st
        if st != "RUNNING":
            issues.append(f"supervisor {name} not RUNNING: {st}")

    health_rows = [_comfyui_health(p) for p in COMFY_PORTS]
    checks["comfyui_health"] = health_rows
    for row in health_rows:
        if not row.get("ok"):
            issues.append(f"ComfyUI :{row.get('port')} unhealthy: {row}")

    cuda_map: dict[str, str | None] = {}
    for port in COMFY_PORTS:
        pid = _comfyui_pid(port)
        cuda_map[port] = _cuda_visible_devices(pid)
    checks["cuda_visible_devices"] = cuda_map
    if cuda_map.get("8000") != "0":
        issues.append(f"comfyui0 CUDA_VISIBLE_DEVICES expected 0, got {cuda_map.get('8000')}")
    if cuda_map.get("8001") != "1":
        issues.append(f"comfyui1 CUDA_VISIBLE_DEVICES expected 1, got {cuda_map.get('8001')}")

    nodes = comfyui_nodes_list()
    checks["backend_comfyui_nodes"] = nodes
    if len(nodes) != 2:
        issues.append(f"backend comfyui_nodes_list expected 2 nodes, got {len(nodes)}: {nodes}")
    else:
        for port in COMFY_PORTS:
            if not any(f":{port}" in u for u in nodes):
                issues.append(f"backend nodes missing port {port}: {nodes}")

    os.environ.setdefault(
        "COMFYUI_NODES",
        "http://127.0.0.1:8000,http://127.0.0.1:8001",
    )
    pool = GPUPool.from_env()
    checks["gpu_pool_urls"] = [n.comfyui_url for n in pool.nodes]
    if len(pool.nodes) != 2:
        issues.append(f"GPUPool.from_env expected 2 nodes, got {len(pool.nodes)}")

    report["phase0"] = {"checks": checks, "issues": list(issues)}
    return issues


def phase1_pool_logic(report: dict) -> list[str]:
    issues: list[str] = []
    pool = GPUPool.from_env()
    n1 = pool.get_available_node(required_vram=16, estimated_duration_sec=30)
    pool.mark_busy_by_url(n1.comfyui_url, "smoke-a", 120)
    n2 = pool.get_available_node(required_vram=16, estimated_duration_sec=30)
    pool.mark_free_by_url(n1.comfyui_url)
    ok = n1.comfyui_url.rstrip("/") != n2.comfyui_url.rstrip("/")
    report["phase1"] = {
        "n1": n1.comfyui_url,
        "n2": n2.comfyui_url,
        "distinct": ok,
    }
    if not ok:
        issues.append(f"pool logic: n1==n2 ({n1.comfyui_url})")
    return issues


def _build_video_payload(node_id: str) -> dict:
    payload = dict(WAN_PAYLOAD)
    payload["node_id"] = node_id
    return payload


def _submit_video(client: httpx.Client, token: str, node_id: str) -> dict:
    t0 = time.time()
    r = client.post(
        f"{BASE}/api/tasks/video",
        headers=headers(token),
        json=_build_video_payload(node_id),
        timeout=60,
    )
    body = {}
    try:
        body = r.json()
    except Exception:
        body = {"raw": r.text[:300]}
    return {
        "node_id": node_id,
        "http_status": r.status_code,
        "task_id": body.get("task_id"),
        "body": body,
        "submit_sec": round(time.time() - t0, 2),
        "error": None if r.status_code < 400 else str(body)[:300],
    }


def _poll_task(client: httpx.Client, token: str, task_id: str) -> dict:
    deadline = time.time() + POLL_TIMEOUT
    last: dict = {}
    while time.time() < deadline:
        r = client.get(
            f"{BASE}/api/tasks/{task_id}",
            headers=headers(token),
            timeout=30,
        )
        r.raise_for_status()
        last = r.json()
        if last.get("status") in ("completed", "failed", "cancelled"):
            return last
        time.sleep(POLL_INTERVAL)
    last["status"] = last.get("status") or "timeout"
    last["error"] = last.get("error") or f"poll timeout after {POLL_TIMEOUT}s"
    return last


def _query_task_nodes(task_ids: list[str]) -> list[dict]:
    if not DB_PATH.is_file():
        return []
    conn = sqlite3.connect(DB_PATH)
    try:
        placeholders = ",".join("?" for _ in task_ids)
        cur = conn.execute(
            f"SELECT id, comfyui_node_url, status, comfyui_prompt_id "
            f"FROM tasks WHERE id IN ({placeholders})",
            task_ids,
        )
        return [
            {
                "id": row[0],
                "comfyui_node_url": row[1],
                "status": row[2],
                "comfyui_prompt_id": row[3],
            }
            for row in cur.fetchall()
        ]
    finally:
        conn.close()


def _node_ports_from_db(rows: list[dict]) -> set[str]:
    ports: set[str] = set()
    for row in rows:
        url = (row.get("comfyui_node_url") or "").strip()
        for port in COMFY_PORTS:
            if f":{port}" in url:
                ports.add(port)
    return ports


def _comfyui_queues() -> dict:
    out: dict = {}
    for port in COMFY_PORTS:
        try:
            r = httpx.get(f"http://127.0.0.1:{port}/queue", timeout=5)
            if r.status_code == 200:
                data = r.json()
                out[port] = {
                    "queue_running": len(data.get("queue_running") or []),
                    "queue_pending": len(data.get("queue_pending") or []),
                }
            else:
                out[port] = {"error": f"http {r.status_code}"}
        except Exception as exc:
            out[port] = {"error": str(exc)}
    return out


def phase2_concurrent_wan(report: dict) -> tuple[list[str], str]:
    """返回 (issues, verdict: pass|warn|fail)。"""
    issues: list[str] = []
    nvidia_samples: list[dict] = []
    stop_event = threading.Event()

    def _sampler() -> None:
        for i in range(NVIDIA_SAMPLE_COUNT):
            if stop_event.is_set():
                break
            nvidia_samples.append({"t": _now_iso(), "gpus": _sample_nvidia()})
            if i + 1 < NVIDIA_SAMPLE_COUNT:
                time.sleep(NVIDIA_SAMPLE_INTERVAL)

    sampler_thread = threading.Thread(target=_sampler, daemon=True)
    sampler_thread.start()

    t0 = time.time()
    node_a = f"dual-gpu-a-{uuid.uuid4().hex[:8]}"
    node_b = f"dual-gpu-b-{uuid.uuid4().hex[:8]}"

    with httpx.Client(timeout=60.0) as client:
        token = login(load_admin_username(), load_admin_password())

        with ThreadPoolExecutor(max_workers=2) as ex:
            futs = {
                ex.submit(_submit_video, client, token, node_a): "a",
                ex.submit(_submit_video, client, token, node_b): "b",
            }
            submits: list[dict] = []
            for fut in as_completed(futs):
                submits.append(fut.result())

        submits.sort(key=lambda x: x.get("node_id") or "")
        bad_submit = [s for s in submits if s.get("http_status", 0) >= 400 or not s.get("task_id")]
        if bad_submit:
            for s in bad_submit:
                issues.append(f"submit failed {s.get('node_id')}: {s.get('error')}")
            stop_event.set()
            sampler_thread.join(timeout=2)
            report["phase2"] = {
                "submits": submits,
                "issues": issues,
                "wall_sec": round(time.time() - t0, 1),
            }
            return issues, "fail"

        task_ids = [s["task_id"] for s in submits if s.get("task_id")]
        db_seen_processing = False
        poll_results: list[dict] = []

        deadline = time.time() + POLL_TIMEOUT
        pending = set(task_ids)
        while pending and time.time() < deadline:
            if not db_seen_processing:
                db_rows = _query_task_nodes(task_ids)
                if any(r.get("comfyui_node_url") for r in db_rows):
                    db_seen_processing = True
                    report.setdefault("phase2_mid", {})["db_early"] = db_rows

            for tid in list(pending):
                r = client.get(
                    f"{BASE}/api/tasks/{tid}",
                    headers=headers(token),
                    timeout=30,
                )
                r.raise_for_status()
                task = r.json()
                st = task.get("status")
                if st in ("completed", "failed", "cancelled"):
                    poll_results.append(
                        {
                            "task_id": tid,
                            "status": st,
                            "result": str(task.get("result") or "")[:120],
                            "error": task.get("error"),
                        }
                    )
                    pending.discard(tid)
            if pending:
                time.sleep(POLL_INTERVAL)

        for tid in pending:
            poll_results.append(
                {
                    "task_id": tid,
                    "status": "timeout",
                    "result": None,
                    "error": f"poll timeout after {POLL_TIMEOUT}s",
                }
            )

    stop_event.set()
    sampler_thread.join(timeout=NVIDIA_SAMPLE_INTERVAL + 2)

    db_rows = _query_task_nodes(task_ids)
    ports_seen = _node_ports_from_db(db_rows)
    routing_ok = ports_seen == set(COMFY_PORTS)
    tasks_ok = all(
        p.get("status") == "completed" and p.get("result")
        for p in poll_results
    )
    dual_util = _dual_gpu_util_seen(nvidia_samples)
    queue_snap = _comfyui_queues()

    if not tasks_ok:
        for p in poll_results:
            if p.get("status") != "completed" or not p.get("result"):
                issues.append(
                    f"task {p.get('task_id')} status={p.get('status')} error={p.get('error')}"
                )
    if not routing_ok:
        issues.append(
            f"routing: expected ports {COMFY_PORTS}, got {sorted(ports_seen)} db={db_rows}"
        )

    if not issues and dual_util:
        verdict = "pass"
    elif routing_ok and tasks_ok and not dual_util:
        verdict = "warn"
        issues.append(
            "nvidia-smi did not capture simultaneous util on GPU0 and GPU1 (>5%)"
        )
    else:
        verdict = "fail"

    report["phase2"] = {
        "submits": submits,
        "poll_results": poll_results,
        "db_rows": db_rows,
        "ports_seen": sorted(ports_seen),
        "routing_ok": routing_ok,
        "tasks_ok": tasks_ok,
        "nvidia_samples": nvidia_samples,
        "dual_gpu_util_seen": dual_util,
        "queue_snapshots": queue_snap,
        "wall_sec": round(time.time() - t0, 1),
        "verdict": verdict,
        "issues": list(issues),
    }
    return issues, verdict


def main() -> int:
    if os.environ.get("AGENT_MOCK_GENERATION", "").lower() in ("1", "true", "yes"):
        print("FAIL: AGENT_MOCK_GENERATION is enabled")
        return 2

    report: dict = {
        "ok": False,
        "started_at": _now_iso(),
        "issues": [],
        "verdict": "fail",
    }
    all_issues: list[str] = []

    p0 = phase0_preflight(report)
    all_issues.extend(p0)
    if p0:
        report["issues"] = all_issues
        report["finished_at"] = _now_iso()
        OUT.parent.mkdir(parents=True, exist_ok=True)
        OUT.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
        print(json.dumps(report, ensure_ascii=False, indent=2))
        return 2

    p1 = phase1_pool_logic(report)
    all_issues.extend(p1)
    if p1:
        report["issues"] = all_issues
        report["finished_at"] = _now_iso()
        OUT.parent.mkdir(parents=True, exist_ok=True)
        OUT.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
        print(json.dumps(report, ensure_ascii=False, indent=2))
        return 2

    # 探针进程内重置池，避免污染 backend 进程内状态；真实路由看 Phase2 DB 字段
    reset_gpu_pool_for_tests(GPUPool.from_env())

    p2_issues, verdict = phase2_concurrent_wan(report)
    all_issues.extend(p2_issues)
    report["verdict"] = verdict
    report["ok"] = verdict in ("pass", "warn") and not any(
        i for i in p2_issues if verdict == "fail"
    )
    if verdict == "warn":
        report["ok"] = True
    report["issues"] = all_issues
    report["finished_at"] = _now_iso()

    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(report, ensure_ascii=False, indent=2))

    if verdict == "pass":
        return 0
    if verdict == "warn":
        return 0
    return 1


if __name__ == "__main__":
    sys.exit(main())
