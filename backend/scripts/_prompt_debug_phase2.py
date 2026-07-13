#!/usr/bin/env python3
"""Prompt 调试阶段二：Wan i2v V1–V4 + backend.out.log trace 解析。"""
from __future__ import annotations

import ast
import asyncio
import json
import re
import sys
import time
import uuid
from pathlib import Path

import httpx

BASE = "http://127.0.0.1:7788"
LOG_PATH = Path("/root/autodl-tmp/logs/backend.out.log")
PHASE2_RUN_LOG = Path("/root/autodl-tmp/logs/prompt_debug_phase2_run.log")
V3_RETEST_OUT = Path("/root/autodl-tmp/logs/prompt_debug_v3_retest.json")
V1_FLUX_REF_CACHE = Path("/tmp/v1_flux_ref.png")
POLL_INTERVAL = 5
POLL_TIMEOUT = 1800
V1_REF_FILENAME = "ComfyUI_00024_.png"

PROMPT_ZH = "镜头缓缓后拉，女人转身离开，雨水打在青石板上"
PROMPT_EN = "camera slowly pulls back, woman turns and walks away, rain on cobblestones"

CASES = [
    {
        "id": "V1",
        "prompt": PROMPT_ZH,
        "ref_key": "A",
        "quality_preset_id": "cinematic",
    },
    {
        "id": "V2",
        "prompt": PROMPT_EN,
        "ref_key": "A",
        "quality_preset_id": "cinematic",
    },
    {
        "id": "V3",
        "prompt": PROMPT_ZH,
        "ref_key": "B",
        "quality_preset_id": "cinematic",
    },
    {
        "id": "V4",
        "prompt": PROMPT_ZH,
        "ref_key": "B",
        "quality_preset_id": None,
    },
]


def load_password() -> str:
    env_path = Path(__file__).resolve().parents[1] / ".env"
    for line in env_path.read_text().splitlines():
        if line.startswith("SEED_TESTUSER_PASSWORD="):
            return line.split("=", 1)[1].strip()
    raise RuntimeError("SEED_TESTUSER_PASSWORD not found")


def summarize(text: str | None, n: int = 150) -> str:
    if not text:
        return ""
    s = " ".join(str(text).split())
    return s if len(s) <= n else s[: n - 1] + "…"


def parse_traces_from_log(trace_ids: dict[str, str], log_start_offset: int) -> dict[str, dict]:
    text = LOG_PATH.read_text(encoding="utf-8", errors="replace")[log_start_offset:]
    out: dict[str, dict] = {v: {} for v in trace_ids.values()}
    id_by_short = {tid: cid for cid, tid in trace_ids.items()}

    for line in text.splitlines():
        if "[AIStudio:trace]" not in line:
            continue
        for tid, case_id in id_by_short.items():
            if tid not in line:
                continue
            if "L1 SUBMIT" in line or "SUBMIT model=" in line:
                out[tid]["l1"] = line
            elif "L2 RECEIVED" in line:
                m = re.search(r"prompt_len=(\d+)", line)
                out[tid]["l2_prompt_len"] = int(m.group(1)) if m else None
                out[tid]["l2_line"] = line
            elif "L3 TRANSLATED" in line:
                m_b = re.search(r"before_len=(\d+)", line)
                m_a = re.search(r"after_len=(\d+)", line)
                m_f = re.search(r"final_len=(\d+)", line)
                out[tid]["l3_before_len"] = int(m_b.group(1)) if m_b else None
                out[tid]["l3_after_len"] = int(m_a.group(1)) if m_a else None
                out[tid]["l3_final_len"] = int(m_f.group(1)) if m_f else None
                out[tid]["l3_line"] = line
            elif "L4 WORKFLOW" in line:
                brace = line.find("{", line.find("L4 WORKFLOW"))
                if brace > 0:
                    try:
                        out[tid]["l4"] = ast.literal_eval(line[brace:])
                    except (SyntaxError, ValueError):
                        out[tid]["l4_raw"] = line[brace:]
                out[tid]["l4_line"] = line

    return {cid: out[tid] for cid, tid in trace_ids.items()}


async def login(client: httpx.AsyncClient) -> str:
    r = await client.post(
        f"{BASE}/api/auth/login",
        json={"username_or_email": "testuser", "password": load_password()},
    )
    r.raise_for_status()
    return r.json()["access_token"]


def extract_v1_ref_url() -> str:
    """从 backend.out.log 或 phase2 跑批日志提取 V1 Flux 参考图完整 URL。"""
    pattern = re.compile(
        rf"/api/view\?filename={re.escape(V1_REF_FILENAME)}[^ \n\"']+"
    )
    for path in (LOG_PATH, PHASE2_RUN_LOG):
        if not path.is_file():
            continue
        text = path.read_text(encoding="utf-8", errors="replace")
        matches = pattern.findall(text)
        if not matches:
            continue
        # 优先取含完整 media ticket 的最长 URL（run.log 可能被截断）
        return max(matches, key=len)
    raise RuntimeError(f"cannot find V1 ref URL for {V1_REF_FILENAME}")


async def download_authed_url(
    client: httpx.AsyncClient, token: str, url: str, dest: Path
) -> Path:
    headers = {"Authorization": f"Bearer {token}"}
    r = await client.get(f"{BASE}{url}", headers=headers, timeout=120.0)
    r.raise_for_status()
    dest.write_bytes(r.content)
    return dest


async def upload_image_file(
    client: httpx.AsyncClient, token: str, path: Path, *, filename: str | None = None
) -> str:
    upload_headers = {"Authorization": f"Bearer {token}"}
    name = filename or path.name
    mime = "image/png" if name.lower().endswith(".png") else "image/jpeg"
    with path.open("rb") as f:
        ur = await client.post(
            f"{BASE}/api/upload/image",
            headers=upload_headers,
            files={"file": (name, f, mime)},
            timeout=60,
        )
    ur.raise_for_status()
    url = ur.json().get("url")
    if not url:
        raise RuntimeError("upload missing url")
    return url


async def upload_view_url_as_uploads(
    client: httpx.AsyncClient, token: str, view_url: str, cache_path: Path
) -> str:
    await download_authed_url(client, token, view_url, cache_path)
    return await upload_image_file(client, token, cache_path)


async def poll_task(client: httpx.AsyncClient, token: str, task_id: str) -> dict:
    headers = {"Authorization": f"Bearer {token}"}
    deadline = time.time() + POLL_TIMEOUT
    while time.time() < deadline:
        r = await client.get(f"{BASE}/api/tasks/{task_id}", headers=headers)
        r.raise_for_status()
        data = r.json()
        status = data.get("status")
        print(f"  poll {task_id[:8]}… status={status}", flush=True)
        if status in ("completed", "failed"):
            return data
        await asyncio.sleep(POLL_INTERVAL)
    raise TimeoutError(f"task {task_id} timeout")


async def prepare_refs(client: httpx.AsyncClient, token: str) -> tuple[str, str]:
    headers = {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}
    # 来源 A：flux 16:9
    tid = str(uuid.uuid4())
    r = await client.post(
        f"{BASE}/api/tasks/image",
        headers=headers,
        json={
            "model": "flux-dev",
            "prompt": "a woman standing in a rain-soaked hutong, photorealistic, cinematic",
            "quality_preset_id": "cinematic",
            "ratio": "16:9",
            "quality": "2K",
            "count": 1,
            "node_id": "phase2-flux-ref",
            "trace_id": tid,
        },
        timeout=120,
    )
    r.raise_for_status()
    img_task = r.json().get("task_id") or (r.json().get("task_ids") or [None])[0]
    print(f"[prep] flux image task {img_task}", flush=True)
    img = await poll_task(client, token, img_task)
    if img.get("status") != "completed":
        raise RuntimeError(f"flux ref failed: {img.get('error')}")
    url_a = img.get("result")
    if not url_a:
        raise RuntimeError("flux ref missing result url")

    # 来源 B：将来源 A 同图经 /api/upload/image 上传（同内容双路径）
    url_b = await upload_view_url_as_uploads(client, token, url_a, V1_FLUX_REF_CACHE)
    print(f"[prep] ref A={url_a[:60]}…", flush=True)
    print(f"[prep] ref B={url_b[:60]}…", flush=True)
    return url_a, url_b


def build_table(case_id: str, trace: dict, case_meta: dict, task: dict) -> list[dict]:
    l4 = trace.get("l4") or {}
    rows = [
        {"case": case_id, "layer": "L1", "tag": "SUBMIT", "summary": summarize(case_meta["prompt"])},
        {
            "case": case_id,
            "layer": "L2",
            "tag": "RECEIVED",
            "summary": f"prompt_len={trace.get('l2_prompt_len')} preset={case_meta.get('quality_preset_id')}",
        },
        {
            "case": case_id,
            "layer": "L3",
            "tag": "before_len",
            "summary": str(trace.get("l3_before_len")),
        },
        {
            "case": case_id,
            "layer": "L3",
            "tag": "after_len",
            "summary": str(trace.get("l3_after_len")),
        },
        {
            "case": case_id,
            "layer": "L4",
            "tag": "positive",
            "summary": summarize(l4.get("positive_prompt"), 150),
        },
        {
            "case": case_id,
            "layer": "L4",
            "tag": "negative",
            "summary": summarize(l4.get("negative_prompt"), 150),
        },
        {
            "case": case_id,
            "layer": "L4",
            "tag": "steps/frames",
            "summary": (
                f"steps={l4.get('steps')} cfg={l4.get('cfg')} "
                f"size={l4.get('width')}x{l4.get('height')} frames={l4.get('num_frames')}"
            ),
        },
        {
            "case": case_id,
            "layer": "—",
            "tag": "reference",
            "summary": l4.get("reference_filename") or "(empty)",
        },
        {
            "case": case_id,
            "layer": "—",
            "tag": "task_result",
            "summary": summarize(task.get("result"), 120),
        },
    ]
    return rows


async def run_phase(label: str) -> dict:
    log_start = LOG_PATH.stat().st_size if LOG_PATH.is_file() else 0
    trace_ids: dict[str, str] = {c["id"]: str(uuid.uuid4()) for c in CASES}
    results: dict = {"label": label, "cases": {}, "tables": []}

    async with httpx.AsyncClient(timeout=180.0) as client:
        token = await login(client)
        url_a, url_b = await prepare_refs(client, token)
        refs = {"A": url_a, "B": url_b}
        headers = {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}

        for case in CASES:
            cid = case["id"]
            tid = trace_ids[cid]
            body = {
                "model": "wan-i2v",
                "prompt": case["prompt"],
                "reference_image": refs[case["ref_key"]],
                "ratio": "16:9",
                "resolution": "720P",
                "duration": 3,
                "count": 1,
                "node_id": f"prompt-debug-{cid.lower()}",
                "trace_id": tid,
            }
            if case.get("quality_preset_id"):
                body["quality_preset_id"] = case["quality_preset_id"]
            print(f"\n[{label}] {cid} submit trace_id={tid[:8]}…", flush=True)
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
    for case in CASES:
        cid = case["id"]
        trace = traces.get(cid, {})
        task = results["cases"].get(cid, {})
        results["cases"].setdefault(cid, {})["trace"] = trace
        results["tables"].extend(build_table(cid, trace, case, task))

    return results


async def run_v3_retest() -> dict:
    """V3 补验收：复用 V1 Flux 图，经 uploads 路径跑单次 wan-i2v。"""
    log_start = LOG_PATH.stat().st_size if LOG_PATH.is_file() else 0
    case_id = "V3-retest"
    trace_id = str(uuid.uuid4())
    case_meta = {
        "id": case_id,
        "prompt": PROMPT_ZH,
        "quality_preset_id": "cinematic",
    }
    results: dict = {"label": "v3-retest", "cases": {}, "tables": []}

    async with httpx.AsyncClient(timeout=180.0) as client:
        token = await login(client)
        view_url = extract_v1_ref_url()
        print(f"[v3-retest] V1 ref {view_url[:70]}…", flush=True)
        upload_url = await upload_view_url_as_uploads(
            client, token, view_url, V1_FLUX_REF_CACHE
        )
        print(f"[v3-retest] uploads ref {upload_url[:70]}…", flush=True)

        headers = {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}
        body = {
            "model": "wan-i2v",
            "prompt": PROMPT_ZH,
            "reference_image": upload_url,
            "quality_preset_id": "cinematic",
            "ratio": "16:9",
            "resolution": "720P",
            "duration": 3,
            "count": 1,
            "node_id": "prompt-debug-v3-retest",
            "trace_id": trace_id,
        }
        print(f"[v3-retest] submit trace_id={trace_id[:8]}…", flush=True)
        r = await client.post(f"{BASE}/api/tasks/video", headers=headers, json=body)
        if r.status_code >= 400:
            results["cases"][case_id] = {"error": r.text, "status_code": r.status_code}
            return results
        task_id = r.json().get("task_id") or (r.json().get("task_ids") or [None])[0]
        task = await poll_task(client, token, task_id)
        results["cases"][case_id] = {
            "task_id": task_id,
            "status": task.get("status"),
            "error": task.get("error"),
            "result": task.get("result"),
            "trace_id": trace_id,
            "reference_view_url": view_url,
            "reference_upload_url": upload_url,
        }
        if task.get("status") == "completed" and task.get("result"):
            mp4_path = Path("/tmp/v3_retest_result.mp4")
            await download_authed_url(client, token, task["result"], mp4_path)
            results["cases"][case_id]["mp4_path"] = str(mp4_path)
            debug_dir = Path("/root/debug_videos")
            debug_dir.mkdir(parents=True, exist_ok=True)
            dest = debug_dir / "v3_retest_result.mp4"
            dest.write_bytes(mp4_path.read_bytes())
            results["cases"][case_id]["mp4_debug_path"] = str(dest)

    traces = parse_traces_from_log({case_id: trace_id}, log_start)
    trace = traces.get(case_id, {})
    task = results["cases"].get(case_id, {})
    results["cases"].setdefault(case_id, {})["trace"] = trace
    results["tables"].extend(build_table(case_id, trace, case_meta, task))
    return results


def main() -> int:
    label = sys.argv[1] if len(sys.argv) > 1 else "postfix"
    if label == "v3-retest":
        data = asyncio.run(run_v3_retest())
        out = V3_RETEST_OUT
    else:
        out = Path(f"/root/autodl-tmp/logs/prompt_debug_phase2_{label}.json")
        data = asyncio.run(run_phase(label))
    out.write_text(json.dumps(data, ensure_ascii=False, indent=2))
    print(f"\nWrote {out}")
    for row in data["tables"]:
        print(f"{row['case']} {row['layer']} {row['tag']}: {row['summary']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
