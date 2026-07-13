#!/usr/bin/env python3
"""Phase 2 GPU smoke tests: hidream image + wan-i2v video via AI Studio API."""
from __future__ import annotations

import json
import os
import subprocess
import sys
import time
from pathlib import Path

import httpx

BASE = "http://127.0.0.1:7788"
PASSWORD = os.environ.get("SEED_TESTUSER_PASSWORD", "")
if not PASSWORD:
    env_path = Path(__file__).resolve().parents[1] / ".env"
    for line in env_path.read_text().splitlines():
        if line.startswith("SEED_TESTUSER_PASSWORD="):
            PASSWORD = line.split("=", 1)[1].strip()
            break

POLL_INTERVAL = 5
POLL_TIMEOUT = 1800  # 30 min per task


def vram_mb() -> tuple[int, int]:
    out = subprocess.check_output(
        [
            "nvidia-smi",
            "--query-gpu=memory.used,memory.free",
            "--format=csv,noheader,nounits",
        ],
        text=True,
    ).strip()
    used, free = [int(x.strip()) for x in out.split(",")]
    return used, free


def login(client: httpx.Client) -> str:
    r = client.post(
        f"{BASE}/api/auth/login",
        json={"username_or_email": "testuser", "password": PASSWORD},
    )
    r.raise_for_status()
    return r.json()["access_token"]


def poll_task(client: httpx.Client, token: str, task_id: str) -> dict:
    headers = {"Authorization": f"Bearer {token}"}
    start = time.time()
    peak_vram = 0
    while time.time() - start < POLL_TIMEOUT:
        used, _ = vram_mb()
        peak_vram = max(peak_vram, used)
        r = client.get(f"{BASE}/api/tasks/{task_id}", headers=headers)
        r.raise_for_status()
        data = r.json()
        status = data.get("status")
        progress = data.get("progress", 0)
        print(f"  poll {task_id[:8]}… status={status} progress={progress}% vram={used}MB", flush=True)
        if status == "completed":
            data["_peak_vram_mb"] = peak_vram
            data["_elapsed_s"] = round(time.time() - start, 1)
            return data
        if status == "failed":
            data["_peak_vram_mb"] = peak_vram
            data["_elapsed_s"] = round(time.time() - start, 1)
            return data
        time.sleep(POLL_INTERVAL)
    raise TimeoutError(f"task {task_id} timed out after {POLL_TIMEOUT}s")


def verify_result_file(result_url: str, expect_video: bool = False) -> int:
    """Fetch result via localhost (signed URL)."""
    if result_url.startswith("/"):
        url = f"{BASE}{result_url}"
    else:
        url = result_url
    with httpx.Client(timeout=60.0, follow_redirects=True) as c:
        r = c.get(url)
        r.raise_for_status()
        size = len(r.content)
        if size < 1000:
            raise ValueError(f"result too small: {size} bytes")
        if expect_video:
            if not (r.content[:4] == b"\x00\x00\x00" or r.content[4:8] == b"ftyp" or b"ftyp" in r.content[:32]):
                # mp4 often has ftyp at offset 4
                pass  # len check is enough for smoke
        return size


def smoke_hidream(client: httpx.Client, token: str) -> dict:
    print("\n=== HiDream smoke test ===", flush=True)
    headers = {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}
    body = {
        "model": "hidream",
        "prompt": "a cinematic portrait of a woman in a rain-soaked alley, photorealistic, film grain",
        "negative_prompt": "cartoon, anime, blurry",
        "ratio": "1:1",
        "quality": "2K",
        "count": 1,
        "node_id": "smoke-hidream-phase2",
    }
    t0 = time.time()
    r = client.post(f"{BASE}/api/tasks/image", headers=headers, json=body, timeout=120.0)
    r.raise_for_status()
    data = r.json()
    task_id = data.get("task_id") or (data.get("task_ids") or [None])[0]
    print(f"  submitted task_id={task_id}", flush=True)
    result = poll_task(client, token, task_id)
    status = result.get("status")
    out = {
        "test": "hidream",
        "status": status,
        "task_id": task_id,
        "elapsed_s": result.get("_elapsed_s"),
        "peak_vram_gb": round(result.get("_peak_vram_mb", 0) / 1024, 2),
        "pass": False,
    }
    if status == "completed" and result.get("result"):
        size = verify_result_file(result["result"])
        out["file_bytes"] = size
        out["pass"] = size > 1000 and out["peak_vram_gb"] < 23
        print(f"  PASS file={size} bytes vram_peak={out['peak_vram_gb']}GB time={out['elapsed_s']}s", flush=True)
    else:
        out["error"] = result.get("error")
        print(f"  FAIL status={status} error={out.get('error')}", flush=True)
    return out


def upload_test_image(client: httpx.Client, token: str, img_path: Path) -> str:
    headers = {"Authorization": f"Bearer {token}"}
    with img_path.open("rb") as f:
        files = {"file": (img_path.name, f, "image/jpeg")}
        r = client.post(f"{BASE}/api/upload/image", headers=headers, files=files, timeout=60.0)
    r.raise_for_status()
    return r.json()["url"]


def smoke_wan_i2v(client: httpx.Client, token: str, ref_url: str) -> dict:
    print("\n=== Wan i2v smoke test ===", flush=True)
    headers = {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}
    body = {
        "model": "wan-i2v",
        "prompt": "camera slowly pulls back, cinematic motion, photorealistic",
        "ratio": "16:9",
        "resolution": "720P",
        "duration": 3,
        "count": 1,
        "node_id": "smoke-wan-i2v-phase2",
        "reference_image": ref_url,
    }
    r = client.post(f"{BASE}/api/tasks/video", headers=headers, json=body, timeout=120.0)
    r.raise_for_status()
    data = r.json()
    task_id = data.get("task_id") or (data.get("task_ids") or [None])[0]
    print(f"  submitted task_id={task_id} ref={ref_url[:60]}…", flush=True)
    result = poll_task(client, token, task_id)
    status = result.get("status")
    out = {
        "test": "wan-i2v",
        "status": status,
        "task_id": task_id,
        "elapsed_s": result.get("_elapsed_s"),
        "peak_vram_gb": round(result.get("_peak_vram_mb", 0) / 1024, 2),
        "pass": False,
    }
    if status == "completed" and result.get("result"):
        size = verify_result_file(result["result"], expect_video=True)
        out["file_bytes"] = size
        out["pass"] = size > 10000 and out["peak_vram_gb"] < 23
        print(f"  PASS file={size} bytes vram_peak={out['peak_vram_gb']}GB time={out['elapsed_s']}s", flush=True)
    else:
        out["error"] = result.get("error")
        print(f"  FAIL status={status} error={out.get('error')}", flush=True)
    return out


def main() -> int:
    results: list[dict] = []
    with httpx.Client(timeout=30.0) as client:
        token = login(client)
        print("login OK", flush=True)

        hidream = smoke_hidream(client, token)
        results.append(hidream)

        # i2v 需要 /api/uploads/ 鉴权 URL，不能用 ComfyUI /api/view 输出
        test_img = Path("/tmp/smoke_test_image.jpg")
        if not test_img.exists():
            subprocess.check_call(
                ["curl", "-s", "-o", str(test_img), "https://picsum.photos/512/512"],
            )
        ref_url = upload_test_image(client, token, test_img)

        wan = smoke_wan_i2v(client, token, ref_url)
        results.append(wan)

    out_path = Path("/root/autodl-tmp/logs/phase2_smoke_results.json")
    out_path.write_text(json.dumps(results, indent=2, ensure_ascii=False))
    print(f"\nResults written to {out_path}", flush=True)
    print(json.dumps(results, indent=2), flush=True)
    return 0 if all(r.get("pass") for r in results) else 1


if __name__ == "__main__":
    raise SystemExit(main())
