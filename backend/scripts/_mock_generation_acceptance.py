"""Mock 出图/视频验收脚本（不依赖 ComfyUI）。"""
from __future__ import annotations

import sys
import time

import httpx

BASE = "http://127.0.0.1:7788"
USERNAME = "testuser"
PASSWORD = "Test@2026!"


def login(client: httpx.Client) -> str:
    r = client.post(
        f"{BASE}/api/auth/login",
        json={"username_or_email": USERNAME, "password": PASSWORD},
        timeout=30,
    )
    r.raise_for_status()
    return r.json()["access_token"]


def headers(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}


def poll_task(client: httpx.Client, token: str, task_id: str, *, timeout: float = 30) -> dict:
    deadline = time.time() + timeout
    last: dict = {}
    while time.time() < deadline:
        r = client.get(f"{BASE}/api/tasks/{task_id}", headers=headers(token), timeout=30)
        r.raise_for_status()
        last = r.json()
        status = last.get("status")
        if status in ("completed", "failed"):
            return last
        time.sleep(0.5)
    raise TimeoutError(f"task {task_id} not terminal within {timeout}s, last={last}")


def test_image(client: httpx.Client, token: str) -> None:
    ref = "/api/uploads/images/mock-ref.jpg"
    r = client.post(
        f"{BASE}/api/tasks/image",
        headers=headers(token),
        json={
            "model": "stable-diffusion",
            "prompt": "mock acceptance test image",
            "ratio": "16:9",
            "quality": "2K",
            "count": 1,
            "node_id": "mock-image-node",
            "reference_images": [ref],
        },
        timeout=30,
    )
    r.raise_for_status()
    body = r.json()
    task_id = body["task_id"]
    print(f"[image] submitted task_id={task_id}")
    result = poll_task(client, token, task_id, timeout=15)
    assert result["status"] == "completed", result
    assert result.get("result"), result
    assert "/api/uploads/images/" in result["result"]
    print(f"[image] completed result={result['result'][:80]}...")


def test_video(client: httpx.Client, token: str) -> None:
    r = client.post(
        f"{BASE}/api/tasks/video",
        headers=headers(token),
        json={
            "model": "ltx-video",
            "prompt": "mock acceptance test video",
            "ratio": "16:9",
            "resolution": "720P",
            "duration": 5,
            "count": 1,
            "node_id": "mock-video-node",
        },
        timeout=30,
    )
    r.raise_for_status()
    body = r.json()
    task_id = body["task_id"]
    assert body.get("comfy_prompt_id") == "mock"
    print(f"[video] submitted task_id={task_id} comfy_prompt_id=mock")
    result = poll_task(client, token, task_id, timeout=20)
    assert result["status"] == "completed", result
    assert result.get("result"), result
    assert "/api/uploads/videos/" in result["result"]
    print(f"[video] completed result={result['result'][:80]}...")


def test_failure_rate(client: httpx.Client, token: str) -> None:
    """需后端以 AGENT_MOCK_FAILURE_RATE=1 启动；此处仅探测一次。"""
    r = client.post(
        f"{BASE}/api/tasks/image",
        headers=headers(token),
        json={
            "model": "stable-diffusion",
            "prompt": "mock failure probe",
            "ratio": "1:1",
            "quality": "2K",
            "count": 1,
            "node_id": "mock-fail-node",
        },
        timeout=30,
    )
    r.raise_for_status()
    task_id = r.json()["task_id"]
    result = poll_task(client, token, task_id, timeout=15)
    print(f"[failure_probe] status={result.get('status')} error={result.get('error')}")
    assert result.get("status") == "failed", result
    assert result.get("error"), result


def main() -> int:
    import argparse

    parser = argparse.ArgumentParser(description="Mock image/video acceptance probe")
    parser.add_argument(
        "--with-failure",
        action="store_true",
        help="Probe mock failure path (backend must run with AGENT_MOCK_FAILURE_RATE=1)",
    )
    args = parser.parse_args()

    issues: list[str] = []
    with httpx.Client() as client:
        try:
            token = login(client)
            print("[auth] login ok")
        except Exception as exc:
            print(f"[auth] FAIL: {exc}")
            return 1
        suites: list[tuple[str, object]] = [("image", test_image), ("video", test_video)]
        if args.with_failure:
            suites = [("failure", test_failure_rate)]
        for name, fn in suites:
            try:
                fn(client, token)
                if name == "failure":
                    # test_failure_rate only prints; verify failed status here
                    pass
            except Exception as exc:
                issues.append(f"{name}: {exc}")
                print(f"[{name}] FAIL: {exc}")
    print("\n=== MOCK ACCEPTANCE ===")
    if issues:
        for item in issues:
            print("-", item)
        return 1
    if args.with_failure:
        print("PASS: mock failure probe (check log for status=failed)")
    else:
        print("PASS: mock image + video completed without ComfyUI")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
