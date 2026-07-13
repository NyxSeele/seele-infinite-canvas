#!/usr/bin/env python3
"""G35: HunyuanVideo registry + weights + workflow structure probe (no GPU)."""
from __future__ import annotations

import json
import sys
from pathlib import Path

BACKEND_ROOT = Path(__file__).resolve().parents[1]
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

from comfyui.client import (
    HUNYUAN_CKPT,
    HUNYUAN_CLIP_L,
    HUNYUAN_CLIP_LLAVA,
    HUNYUAN_DEFAULT_HEIGHT,
    HUNYUAN_DEFAULT_STEPS,
    HUNYUAN_DEFAULT_WIDTH,
    HUNYUAN_VAE,
    build_hunyuan_video_workflow,
)
from model_registry import COMFYUI_LOCAL_PROVIDERS, MODEL_MAP

OUT = Path("/root/autodl-tmp/logs/g35_hunyuan_probe.json")
COMFY = Path("/root/autodl-tmp/ComfyUI/models")


def main() -> int:
    issues: list[str] = []

    entry = MODEL_MAP.get("hunyuan-video")
    if not entry:
        issues.append("MODEL_MAP missing hunyuan-video")
    else:
        if entry.get("video_backend") != "hunyuan":
            issues.append(f"video_backend={entry.get('video_backend')!r}")
        if entry.get("comfyui_model_file") != HUNYUAN_CKPT:
            issues.append(f"comfyui_model_file={entry.get('comfyui_model_file')!r}")
        if not entry.get("default_enabled", False):
            issues.append("default_enabled is False")

    provider = next((p for p in COMFYUI_LOCAL_PROVIDERS if p.get("id") == "hunyuan-video"), None)
    if not provider:
        issues.append("COMFYUI_LOCAL_PROVIDERS missing hunyuan-video")
    elif not provider.get("enabled"):
        issues.append("provider hunyuan-video enabled=False")
    elif provider.get("comfyui_checkpoint") != HUNYUAN_CKPT:
        issues.append(f"provider ckpt={provider.get('comfyui_checkpoint')!r}")

    weight_checks = [
        (COMFY / "diffusion_models" / HUNYUAN_CKPT, 1_000_000_000),
        (COMFY / "vae" / HUNYUAN_VAE, 50_000_000),
        (COMFY / "text_encoders" / HUNYUAN_CLIP_L, 50_000_000),
        (COMFY / "text_encoders" / HUNYUAN_CLIP_LLAVA, 500_000_000),
    ]
    for path, min_size in weight_checks:
        if not path.is_file():
            issues.append(f"missing weight: {path}")
        elif path.stat().st_size < min_size:
            issues.append(f"weight too small: {path} size={path.stat().st_size}")

    wf = build_hunyuan_video_workflow(
        "probe positive",
        "probe negative",
        seed=35,
    )
    class_types = {n.get("class_type") for n in wf.values() if isinstance(n, dict)}
    for required in (
        "EmptyHunyuanLatentVideo",
        "DualCLIPLoader",
        "VAELoader",
        "UNETLoader",
        "KSampler",
    ):
        if required not in class_types:
            issues.append(f"workflow missing {required}")

    sampler = next(n for n in wf.values() if n.get("class_type") == "KSampler")
    latent = next(n for n in wf.values() if n.get("class_type") == "EmptyHunyuanLatentVideo")
    if sampler["inputs"].get("steps") != HUNYUAN_DEFAULT_STEPS:
        issues.append(f"steps={sampler['inputs'].get('steps')}")
    if latent["inputs"].get("width") != HUNYUAN_DEFAULT_WIDTH:
        issues.append(f"width={latent['inputs'].get('width')}")
    if latent["inputs"].get("height") != HUNYUAN_DEFAULT_HEIGHT:
        issues.append(f"height={latent['inputs'].get('height')}")

    out = {
        "ok": not issues,
        "issues": issues,
        "ckpt": HUNYUAN_CKPT,
        "steps": sampler["inputs"].get("steps"),
        "size": [latent["inputs"].get("width"), latent["inputs"].get("height")],
        "class_types": sorted(class_types),
    }
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(out, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(out, ensure_ascii=False, indent=2))
    print(f"Wrote {OUT}")
    return 0 if not issues else 1


if __name__ == "__main__":
    sys.exit(main())
