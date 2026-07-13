#!/usr/bin/env python3
"""G34: wan-fun-inpaint registry + 权重 + workflow 结构探针（无 GPU 出片）。"""
from __future__ import annotations

import json
import sys
from pathlib import Path

BACKEND_ROOT = Path(__file__).resolve().parents[1]
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

from comfyui.client import (
    WAN22_FUN_INPAINT_HIGH,
    WAN22_FUN_INPAINT_LOW,
    build_wan_fun_inpaint_workflow,
)
from model_registry import COMFYUI_LOCAL_PROVIDERS, MODEL_MAP

OUT = Path("/root/autodl-tmp/logs/g34_fun_inpaint_probe.json")
DIFFUSION = Path("/root/autodl-tmp/ComfyUI/models/diffusion_models")


def main() -> int:
    issues: list[str] = []

    entry = MODEL_MAP.get("wan-fun-inpaint")
    if not entry:
        issues.append("MODEL_MAP missing wan-fun-inpaint")
    else:
        if entry.get("video_backend") != "wan":
            issues.append(f"video_backend={entry.get('video_backend')!r}")
        if entry.get("comfyui_model_file") != WAN22_FUN_INPAINT_HIGH:
            issues.append(f"comfyui_model_file={entry.get('comfyui_model_file')!r}")

    provider = next((p for p in COMFYUI_LOCAL_PROVIDERS if p.get("id") == "wan-fun-inpaint"), None)
    if not provider:
        issues.append("COMFYUI_LOCAL_PROVIDERS missing wan-fun-inpaint")
    elif not provider.get("enabled"):
        issues.append("provider wan-fun-inpaint enabled=False")

    for name in (WAN22_FUN_INPAINT_HIGH, WAN22_FUN_INPAINT_LOW):
        path = DIFFUSION / name
        if not path.is_file():
            issues.append(f"missing weight: {path}")
        elif path.stat().st_size < 1_000_000_000:
            issues.append(f"weight too small: {path} size={path.stat().st_size}")

    wf = build_wan_fun_inpaint_workflow(
        "probe positive",
        "probe negative",
        "g34_start.png",
        "g34_end.png",
        width=848,
        height=480,
        duration_sec=5,
        seed=34,
        steps=4,
    )
    class_types = {n.get("class_type") for n in wf.values() if isinstance(n, dict)}
    if "WanFunInpaintToVideo" not in class_types:
        issues.append("workflow missing WanFunInpaintToVideo")
    if sum(1 for n in wf.values() if n.get("class_type") == "LoadImage") != 2:
        issues.append("expected 2 LoadImage nodes")
    unets = {
        n["inputs"]["unet_name"]
        for n in wf.values()
        if n.get("class_type") == "UNETLoader"
    }
    if WAN22_FUN_INPAINT_HIGH not in unets or WAN22_FUN_INPAINT_LOW not in unets:
        issues.append(f"UNET names unexpected: {sorted(unets)}")
    load_imgs = [
        n["inputs"]["image"]
        for n in wf.values()
        if n.get("class_type") == "LoadImage"
    ]
    if load_imgs != ["g34_start.png", "g34_end.png"]:
        issues.append(f"LoadImage filenames={load_imgs!r}")
    steps_vals = {
        n["inputs"]["steps"]
        for n in wf.values()
        if n.get("class_type") == "KSamplerAdvanced"
    }
    if steps_vals != {4}:
        issues.append(f"KSampler steps={steps_vals!r}")

    out = {
        "ok": not issues,
        "issues": issues,
        "registry_id": "wan-fun-inpaint",
        "unet_high": WAN22_FUN_INPAINT_HIGH,
        "unet_low": WAN22_FUN_INPAINT_LOW,
        "workflow_nodes": len(wf),
        "class_types": sorted(class_types),
    }
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(out, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(out, ensure_ascii=False, indent=2))
    print(f"Wrote {OUT}")
    return 0 if not issues else 1


if __name__ == "__main__":
    sys.exit(main())
