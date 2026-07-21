#!/usr/bin/env python3
"""G40: ReActor 结构探针（无 GPU）— use_reactor True/False 至少 2 case。"""
from __future__ import annotations

import json
import sys
from pathlib import Path

BACKEND_ROOT = Path(__file__).resolve().parents[1]
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

from providers.comfyui import _build_flux_pulid_workflow

OUT = Path("/root/autodl-tmp/logs/g40_reactor_probe.json")
TEMPLATE = BACKEND_ROOT / "comfyui" / "workflows" / "flux_pulid_reactor.json"


def _profile() -> dict:
    return {
        "workflow_type": "flux_pulid",
        "generation_defaults": {
            "steps": 20,
            "sampler_name": "euler",
            "scheduler": "simple",
            "pulid_weight": 0.8,
            "guidance": 3.5,
        },
    }


def _class_types(wf: dict) -> set[str]:
    return {n.get("class_type") for n in wf.values() if isinstance(n, dict)}


def main() -> int:
    issues: list[str] = []
    cases: dict = {}

    if not TEMPLATE.is_file():
        issues.append(f"missing template: {TEMPLATE}")
    else:
        tpl = json.loads(TEMPLATE.read_text(encoding="utf-8"))
        if "ReActorFaceSwap" not in _class_types(tpl):
            issues.append("template missing ReActorFaceSwap")
        if tpl.get("9", {}).get("inputs", {}).get("images") != ["60", 0]:
            issues.append("template SaveImage should read node 60")
        cases["template"] = {
            "path": str(TEMPLATE),
            "has_reactor": "ReActorFaceSwap" in _class_types(tpl),
        }

    # Case 1: use_reactor=True
    wf_on = _build_flux_pulid_workflow(
        "a woman in the rain",
        "svdq-fp4_r32-flux.1-dev.safetensors",
        1024,
        1024,
        42,
        _profile(),
        reference_face_image="face.png",
        use_reactor=True,
    )
    types_on = _class_types(wf_on)
    reactor = wf_on.get("60") or {}
    save_imgs = (wf_on.get("9") or {}).get("inputs", {}).get("images")
    source = (reactor.get("inputs") or {}).get("source_image")
    input_img = (reactor.get("inputs") or {}).get("input_image")
    if "ReActorFaceSwap" not in types_on:
        issues.append("use_reactor=True missing ReActorFaceSwap")
    if save_imgs != ["60", 0]:
        issues.append(f"use_reactor=True SaveImage.images={save_imgs!r}")
    if source != ["49", 0]:
        issues.append(f"source_image should be node 49, got {source!r}")
    if input_img != ["8", 0]:
        issues.append(f"input_image should be VAEDecode 8, got {input_img!r}")
    if (reactor.get("inputs") or {}).get("swap_model") != "inswapper_128.onnx":
        issues.append("swap_model expected inswapper_128.onnx")
    cases["use_reactor_true"] = {
        "has_reactor": "ReActorFaceSwap" in types_on,
        "save_images": save_imgs,
        "source_image": source,
        "input_image": input_img,
        "swap_model": (reactor.get("inputs") or {}).get("swap_model"),
    }

    # Case 2: use_reactor=False — 与现网 PuLID 一致
    wf_off = _build_flux_pulid_workflow(
        "a woman in the rain",
        "svdq-fp4_r32-flux.1-dev.safetensors",
        1024,
        1024,
        42,
        _profile(),
        reference_face_image="face.png",
        use_reactor=False,
    )
    types_off = _class_types(wf_off)
    if "ReActorFaceSwap" in types_off:
        issues.append("use_reactor=False still has ReActorFaceSwap")
    if (wf_off.get("9") or {}).get("inputs", {}).get("images") != ["8", 0]:
        issues.append("use_reactor=False SaveImage should read VAEDecode 8")
    if "NunchakuFluxPuLIDApplyV2" not in types_off:
        issues.append("use_reactor=False missing PuLID apply")
    cases["use_reactor_false"] = {
        "has_reactor": "ReActorFaceSwap" in types_off,
        "save_images": (wf_off.get("9") or {}).get("inputs", {}).get("images"),
        "has_pulid": "NunchakuFluxPuLIDApplyV2" in types_off,
    }

    payload = {"ok": not issues, "issues": issues, "cases": cases}
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(payload, ensure_ascii=False, indent=2))
    return 0 if not issues else 1


if __name__ == "__main__":
    raise SystemExit(main())
