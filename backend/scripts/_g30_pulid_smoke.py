#!/usr/bin/env python3
"""G30 PuLID GPU smoke: submit flux-pulid workflow and wait for output."""
from __future__ import annotations

import asyncio
import json
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from providers.comfyui import _build_flux_pulid_workflow
from model_registry import resolve_generation_profile
from comfyui.client import COMFYUI_URL, upload_image_base64
import base64
import httpx

FACE = Path("/tmp/lecun.jpg")
FACE_FALLBACK = Path(__file__).resolve().parent / "g30_probe_face.jpg"
OUT_LOG = Path("/root/autodl-tmp/logs/g30_pulid_smoke.json")
CKPT = "svdq-fp4_r32-flux.1-dev.safetensors"


def _resolve_face_path() -> Path:
    if FACE.is_file():
        return FACE
    if FACE_FALLBACK.is_file():
        return FACE_FALLBACK
    raise FileNotFoundError(f"face image missing: {FACE} or {FACE_FALLBACK}")


def _collect_output_images(history_entry: dict) -> list[dict]:
    outputs: list[dict] = []
    for node in (history_entry.get("outputs") or {}).values():
        for img in node.get("images", []) or []:
            fn = img.get("filename")
            if not fn:
                continue
            sub = img.get("subfolder", "") or ""
            typ = img.get("type", "output")
            p = Path("/root/autodl-tmp/ComfyUI") / typ
            if sub:
                p = p / sub
            p = p / fn
            outputs.append(
                {
                    "path": str(p),
                    "exists": p.is_file(),
                    "size_bytes": p.stat().st_size if p.is_file() else None,
                }
            )
    return outputs


def _execution_error(history_entry: dict) -> str | None:
    status = history_entry.get("status") or {}
    for msg in status.get("messages", []) or []:
        if isinstance(msg, list) and len(msg) >= 2 and msg[0] == "execution_error":
            payload = msg[1]
            if isinstance(payload, dict):
                return str(payload.get("exception_message") or payload)
            return str(payload)
    return None


async def main() -> int:
    face_path = _resolve_face_path()
    if face_path != FACE:
        FACE.write_bytes(face_path.read_bytes())

    b64 = base64.b64encode(face_path.read_bytes()).decode()
    face_name = await upload_image_base64(b64)
    profile = resolve_generation_profile("flux-pulid", CKPT)
    wf = _build_flux_pulid_workflow(
        "portrait photo of a woman in a trench coat, cinematic lighting",
        CKPT,
        512,
        512,
        42,
        profile,
        reference_face_image=face_name,
        pulid_weight=0.8,
    )

    base = COMFYUI_URL.rstrip("/")
    t0 = time.time()

    async with httpx.AsyncClient(timeout=120.0) as client:
        res = await client.post(
            f"{base}/prompt",
            json={"prompt": wf, "client_id": "g30-pulid-smoke"},
        )
        res.raise_for_status()
        prompt_id = res.json()["prompt_id"]
        print(f"submitted prompt_id={prompt_id}")

        deadline = time.time() + 1200
        while time.time() < deadline:
            hist = await client.get(f"{base}/history/{prompt_id}")
            if hist.status_code != 200:
                await asyncio.sleep(5)
                continue
            entry = hist.json().get(prompt_id)
            if not entry:
                await asyncio.sleep(5)
                continue

            status = entry.get("status") or {}
            if not status.get("completed"):
                if _execution_error(entry):
                    OUT_LOG.write_text(
                        json.dumps(entry, ensure_ascii=False, indent=2),
                        encoding="utf-8",
                    )
                    elapsed = round(time.time() - t0, 1)
                    result = {
                        "pass": False,
                        "status_str": status.get("status_str"),
                        "elapsed_sec": elapsed,
                        "prompt_id": prompt_id,
                        "output_images": _collect_output_images(entry),
                        "execution_error": _execution_error(entry),
                    }
                    print(json.dumps(result, ensure_ascii=False, indent=2))
                    return 1
                await asyncio.sleep(5)
                continue

            OUT_LOG.write_text(
                json.dumps(entry, ensure_ascii=False, indent=2),
                encoding="utf-8",
            )
            elapsed = round(time.time() - t0, 1)
            images = _collect_output_images(entry)
            err = _execution_error(entry)
            ok = status.get("status_str") == "success" and any(i.get("exists") for i in images)
            result = {
                "pass": ok,
                "status_str": status.get("status_str"),
                "elapsed_sec": elapsed,
                "prompt_id": prompt_id,
                "output_images": images,
                "execution_error": err,
            }
            print(json.dumps(result, ensure_ascii=False, indent=2))
            if ok:
                print(f"PASS history written to {OUT_LOG}")
                return 0
            return 1

    print("TIMEOUT waiting for PuLID output")
    return 2


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
