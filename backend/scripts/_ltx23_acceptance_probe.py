#!/usr/bin/env python3
"""LTX-2.3 I2AV 启用验收探针：权重落盘 + workflow 结构校验。"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from comfyui.client import build_ltx23_i2av_workflow
from model_registry import COMFYUI_PROVIDER_MAP
from services.registered_model_sync import MODEL_WEIGHT_REQUIREMENTS, weights_ready

OUT = Path("/root/autodl-tmp/logs/ltx23_acceptance.json")
MODEL_ID = "ltx23-i2av"

I2AV_REQUIRED = (
    "UNETLoader",
    "DualCLIPLoader",
    "LoadImage",
    "LTXVImgToVideoInplace",
    "VAELoaderKJ",
    "CreateVideo",
    "SaveVideo",
)
I2AV_AUDIO_REQUIRED = (
    "VHS_LoadAudioUpload",
    "LTXVAudioVAEEncode",
    "LTXVConcatAVLatent",
)


def _probe_workflow(name: str, wf: dict) -> list[str]:
    issues: list[str] = []
    types = {n.get("class_type") for n in wf.values()}
    for required in I2AV_REQUIRED:
        if required not in types:
            issues.append(f"missing {required}")
    if name == "with_audio":
        for required in I2AV_AUDIO_REQUIRED:
            if required not in types:
                issues.append(f"missing audio node {required}")
    if name == "no_audio":
        for forbidden in I2AV_AUDIO_REQUIRED:
            if forbidden in types:
                issues.append(f"unexpected audio node {forbidden} in no-audio workflow")
    unet_nodes = [n for n in wf.values() if n.get("class_type") == "UNETLoader"]
    if not unet_nodes:
        issues.append("no UNETLoader")
    elif "ltx-2.3" not in str(unet_nodes[0].get("inputs", {}).get("unet_name", "")):
        issues.append("UNETLoader not pointing at ltx-2.3 weights")
    return issues


def _check_weights() -> tuple[bool, list[dict]]:
    ok, reason = weights_ready(MODEL_ID)
    rows: list[dict] = []
    spec = MODEL_WEIGHT_REQUIREMENTS.get(MODEL_ID) or {}
    min_bytes: dict[Path, int] = spec.get("min_bytes") or {}
    for path in spec.get("weight_paths") or []:
        p = Path(path)
        size = p.stat().st_size if p.is_file() else 0
        floor = min_bytes.get(p, 1_000_000)
        rows.append(
            {
                "path": str(p),
                "exists": p.is_file(),
                "size": size,
                "min_bytes": floor,
                "ok": p.is_file() and size >= floor,
            }
        )
    return ok, rows


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--json", action="store_true")
    parser.add_argument("--out", type=Path, default=OUT)
    args = parser.parse_args()

    provider = COMFYUI_PROVIDER_MAP.get(MODEL_ID) or {}
    enabled = bool(provider.get("enabled"))
    weights_ok, weight_rows = _check_weights()

    no_audio = build_ltx23_i2av_workflow(
        "slow cinematic push in on subject",
        "blurry, distorted",
        image_filename="probe_ref.png",
        width=1280,
        height=720,
        duration_sec=5,
        audio_filename=None,
    )
    with_audio = build_ltx23_i2av_workflow(
        "a woman singing softly",
        "blurry",
        image_filename="probe_ref.png",
        audio_filename="probe_audio.wav",
        width=1280,
        height=720,
        duration_sec=5,
    )
    no_audio_issues = _probe_workflow("no_audio", no_audio)
    with_audio_issues = _probe_workflow("with_audio", with_audio)

    report = {
        "model_id": MODEL_ID,
        "ltx23_enabled": enabled,
        "weights_ok": weights_ok,
        "weight_rows": weight_rows,
        "no_audio_nodes": len(no_audio),
        "with_audio_nodes": len(with_audio),
        "no_audio_issues": no_audio_issues,
        "with_audio_issues": with_audio_issues,
        "pass": (
            enabled
            and weights_ok
            and not no_audio_issues
            and not with_audio_issues
        ),
    }
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")

    if args.json:
        print(json.dumps(report, ensure_ascii=False, indent=2))
    else:
        print("LTX-2.3 I2AV acceptance probe")
        print(f"  enabled: {enabled}")
        print(f"  weights_ok: {weights_ok}")
        print(f"  no_audio: {len(no_audio)} nodes issues={no_audio_issues or 'none'}")
        print(f"  with_audio: {len(with_audio)} nodes issues={with_audio_issues or 'none'}")
        print(f"  PASS: {report['pass']}")
        print(f"  report: {args.out}")
    return 0 if report["pass"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
