#!/usr/bin/env python3
"""画布验收：qwen-image-restore / qwen-image-material。"""
from __future__ import annotations

import json
import sys
import time
import uuid
from pathlib import Path

import httpx

BASE = "http://127.0.0.1:7788"
OUT_PATH = Path("/root/autodl-tmp/logs/qwen_restore_material_acceptance.json")
POLL_INTERVAL = 3
POLL_TIMEOUT = 600

RESTORE_REF = Path("/root/autodl-tmp/AIStudio/backend/scripts/g30_probe_face.jpg")
MATERIAL_MAIN = Path("/root/autodl-tmp/ComfyUI/output/ComfyUI_00027_.png")
MATERIAL_TEXTURE = Path("/root/autodl-tmp/ComfyUI/input/texture_fur.jpg")


def load_credentials() -> tuple[str, str]:
    env_path = Path(__file__).resolve().parents[1] / ".env"
    password = "Admin@2026!"
    username = "seele"
    if env_path.is_file():
        for line in env_path.read_text(encoding="utf-8").splitlines():
            if line.startswith("SEED_ADMIN_PASSWORD="):
                password = line.split("=", 1)[1].strip().strip('"').strip("'")
    return username, password


def login(client: httpx.Client) -> str:
    username, password = load_credentials()
    r = client.post(
        f"{BASE}/api/auth/login",
        json={"username_or_email": username, "password": password},
    )
    r.raise_for_status()
    return r.json()["access_token"]


def upload_image(client: httpx.Client, token: str, path: Path) -> str:
    headers = {"Authorization": f"Bearer {token}"}
    mime = "image/jpeg" if path.suffix.lower() in (".jpg", ".jpeg") else "image/png"
    with path.open("rb") as fh:
        r = client.post(
            f"{BASE}/api/upload/image",
            headers=headers,
            files={"file": (path.name, fh, mime)},
            timeout=60,
        )
    r.raise_for_status()
    return r.json()["url"]


def poll_task(client: httpx.Client, token: str, task_id: str) -> dict:
    headers = {"Authorization": f"Bearer {token}"}
    start = time.time()
    last: dict = {}
    while time.time() - start < POLL_TIMEOUT:
        r = client.get(f"{BASE}/api/tasks/{task_id}", headers=headers)
        r.raise_for_status()
        last = r.json()
        status = last.get("status")
        print(f"  poll {task_id[:8]}… status={status} progress={last.get('progress', 0)}%", flush=True)
        if status in ("completed", "failed"):
            last["_wall_seconds"] = round(time.time() - start, 1)
            return last
        time.sleep(POLL_INTERVAL)
    raise TimeoutError(f"task {task_id} timed out")


def run_case(
    client: httpx.Client,
    token: str,
    *,
    case_id: str,
    model: str,
    prompt: str,
    reference_images: list[str],
) -> dict:
    headers = {"Authorization": f"Bearer {token}"}
    body = {
        "model": model,
        "prompt": prompt,
        "ratio": "1:1",
        "quality": "1K",
        "count": 1,
        "node_id": f"accept-{case_id}-{uuid.uuid4().hex[:8]}",
        "reference_images": reference_images,
    }
    print(f"\n=== {case_id} model={model} refs={len(reference_images)} ===", flush=True)
    r = client.post(f"{BASE}/api/tasks/image", headers=headers, json=body, timeout=30)
    out = {
        "case": case_id,
        "model": model,
        "prompt": prompt,
        "submit_status": r.status_code,
        "reference_images": reference_images,
    }
    if r.status_code != 200:
        out["error"] = r.text[:500]
        return out
    task_id = r.json().get("task_id")
    out["task_id"] = task_id
    polled = poll_task(client, token, task_id)
    out["status"] = polled.get("status")
    out["generation_seconds"] = polled.get("generation_seconds")
    out["result"] = polled.get("result")
    out["error"] = polled.get("error")
    out["wall_seconds"] = polled.get("_wall_seconds")
    return out


def main() -> int:
    results: dict = {"ok": True, "cases": {}}
    with httpx.Client(timeout=60) as client:
        token = login(client)
        restore_ref = upload_image(client, token, RESTORE_REF)
        material_main = upload_image(client, token, MATERIAL_MAIN)
        material_tex = upload_image(client, token, MATERIAL_TEXTURE)

        cases = [
            {
                "id": "restore",
                "model": "qwen-image-restore",
                "prompt": "修复老照片，提升清晰度和色彩",
                "refs": [restore_ref],
            },
            {
                "id": "material",
                "model": "qwen-image-material",
                "prompt": "将人物服装材质替换为丝绸质感",
                "refs": [material_main, material_tex],
            },
        ]
        for case in cases:
            row = run_case(
                client,
                token,
                case_id=case["id"],
                model=case["model"],
                prompt=case["prompt"],
                reference_images=case["refs"],
            )
            results["cases"][case["id"]] = row
            if row.get("status") != "completed":
                results["ok"] = False

    OUT_PATH.write_text(json.dumps(results, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(results, ensure_ascii=False, indent=2))
    return 0 if results["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
