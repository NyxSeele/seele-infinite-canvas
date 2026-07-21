#!/usr/bin/env python3
"""LTX-2 fp4 启用验收探针：结构校验 + 可选真实出片对比清单。"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from comfyui.client import (
    build_ltx2_fp4_i2v_workflow,
    build_ltx2_fp4_t2v_workflow,
)
from model_registry import COMFYUI_PROVIDER_MAP

ACCEPTANCE_MATRIX = [
    ("T2V", "无参考图 + ltx2-fp4", "workflow_route=text2video"),
    ("I2V", "单图参考 + ltx2-fp4", "LoadImage + LTXVImgToVideoInplace x2"),
    ("FLF2V", "双帧 + ltx2-fp4", "自动切 wan-i2v"),
    ("AUDIO", "audio 开/关", "有声轨 / strip 后仍出片"),
    ("COMPARE", "同 prompt", "Wan 2.6 vs LTX2"),
]


def _probe_workflow(name: str, wf: dict) -> list[str]:
    issues: list[str] = []
    types = {n.get("class_type") for n in wf.values()}
    if name == "t2v":
        if "LTXAVTextEncoderLoader" not in types:
            issues.append("missing LTXAVTextEncoderLoader")
    if name == "i2v":
        for required in ("LoadImage", "LTXVImgToVideoInplace", "LTXVPreprocess"):
            if required not in types:
                issues.append(f"missing {required}")
        if sum(1 for n in wf.values() if n.get("class_type") == "LTXVImgToVideoInplace") < 2:
            issues.append("expected 2x LTXVImgToVideoInplace")
    return issues


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()

    provider = COMFYUI_PROVIDER_MAP.get("ltx2-fp4") or {}
    enabled = bool(provider.get("enabled"))
    t2v = build_ltx2_fp4_t2v_workflow(
        "cinematic sunset over ocean, slow dolly",
        "",
        width=1280,
        height=720,
        duration_sec=5,
        audio=True,
    )
    i2v = build_ltx2_fp4_i2v_workflow(
        "slow push in on subject",
        "",
        image_filename="ref.png",
        width=1280,
        height=720,
        duration_sec=5,
        audio=False,
    )
    t2v_issues = _probe_workflow("t2v", t2v)
    i2v_issues = _probe_workflow("i2v", i2v)

    report = {
        "ltx2_fp4_enabled": enabled,
        "t2v_nodes": len(t2v),
        "i2v_nodes": len(i2v),
        "t2v_issues": t2v_issues,
        "i2v_issues": i2v_issues,
        "acceptance_matrix": [
            {"case": c, "input": i, "expect": e} for c, i, e in ACCEPTANCE_MATRIX
        ],
        "pass": enabled and not t2v_issues and not i2v_issues,
    }
    if args.json:
        print(json.dumps(report, ensure_ascii=False, indent=2))
    else:
        print("LTX-2 fp4 acceptance probe")
        print(f"  enabled: {enabled}")
        print(f"  t2v: {len(t2v)} nodes issues={t2v_issues or 'none'}")
        print(f"  i2v: {len(i2v)} nodes issues={i2v_issues or 'none'}")
        print(f"  PASS: {report['pass']}")
        print("  Manual matrix:")
        for c, i, e in ACCEPTANCE_MATRIX:
            print(f"    - [{c}] {i} → {e}")
    return 0 if report["pass"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
