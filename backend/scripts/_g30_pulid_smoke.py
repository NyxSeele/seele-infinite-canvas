#!/usr/bin/env python3
"""G30 PuLID GPU smoke: submit flux-pulid workflow and wait for output."""
from __future__ import annotations

import asyncio
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
OUT_LOG = Path("/root/autodl-tmp/logs/g30_pulid_smoke.json")


async def main() -> int:
    if not FACE.is_file():
        print(f"MISSING face: {FACE}")
        return 1

    b64 = base64.b64encode(FACE.read_bytes()).decode()
    face_name = await upload_image_base64(b64)
    ckpt = "svdq-int4_r32-flux.1-dev.safetensors"
    profile = resolve_generation_profile("flux-pulid", ckpt)
    wf = _build_flux_pulid_workflow(
        "portrait photo of a woman in a trench coat, cinematic lighting",
        ckpt,
        512,
        512,
        42,
        profile,
        reference_face_image=face_name,
        pulid_weight=0.8,
    )

    async with httpx.AsyncClient(timeout=30.0) as client:
        res = await client.post(
            f"{COMFYUI_URL}/prompt",
            json={"prompt": wf, "client_id": "g30-pulid-smoke"},
        )
        res.raise_for_status()
        prompt_id = res.json()["prompt_id"]
        print(f"submitted prompt_id={prompt_id}")

        deadline = time.time() + 600
        while time.time() < deadline:
            hist = await client.get(f"{COMFYUI_URL}/history/{prompt_id}")
            if hist.status_code == 200:
                data = hist.json()
                if prompt_id in data:
                    OUT_LOG.write_text(
                        __import__("json").dumps(data[prompt_id], ensure_ascii=False, indent=2),
                        encoding="utf-8",
                    )
                    print(f"PASS history written to {OUT_LOG}")
                    return 0
            await asyncio.sleep(5)
    print("TIMEOUT waiting for PuLID output")
    return 2


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
