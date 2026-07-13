#!/usr/bin/env python3
"""G38: LTX2 audio=True/False workflow structure probe (no GPU)."""
from __future__ import annotations

import json
import sys
from pathlib import Path

BACKEND_ROOT = Path(__file__).resolve().parents[1]
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

from comfyui.client import build_ltx2_fp4_t2v_workflow

OUT = Path("/root/autodl-tmp/logs/g38_audio_switch_probe.json")

AUDIO_TYPES = (
    "LTXVAudioVAELoader",
    "LTXVEmptyLatentAudio",
    "LTXVAudioVAEDecode",
    "LTXVConcatAVLatent",
)


def _class_types(wf: dict) -> set[str]:
    return {n.get("class_type") for n in wf.values() if isinstance(n, dict)}


def _create_video_audio(wf: dict):
    for node in wf.values():
        if isinstance(node, dict) and node.get("class_type") == "CreateVideo":
            return node.get("inputs", {}).get("audio")
    return "__missing__"


def main() -> int:
    issues: list[str] = []
    cases: dict = {}

    wf_on = build_ltx2_fp4_t2v_workflow("probe on", "neg", duration_sec=5, seed=1, audio=True)
    types_on = _class_types(wf_on)
    audio_on = _create_video_audio(wf_on)
    missing_on = [t for t in AUDIO_TYPES if t not in types_on]
    if missing_on:
        issues.append(f"audio=True missing types: {missing_on}")
    if not (isinstance(audio_on, list) and len(audio_on) >= 1):
        issues.append(f"audio=True CreateVideo.audio invalid: {audio_on!r}")
    cases["audio_true"] = {
        "has_audio_types": sorted(types_on & set(AUDIO_TYPES)),
        "create_video_audio": audio_on,
    }

    wf_off = build_ltx2_fp4_t2v_workflow("probe off", "neg", duration_sec=5, seed=2, audio=False)
    types_off = _class_types(wf_off)
    audio_off = _create_video_audio(wf_off)
    leftover = [t for t in AUDIO_TYPES if t in types_off]
    if leftover:
        issues.append(f"audio=False still has types: {leftover}")
    if audio_off not in (None,):
        issues.append(f"audio=False CreateVideo.audio should be None, got {audio_off!r}")
    # SeparateAV should also be gone when muted
    if "LTXVSeparateAVLatent" in types_off:
        issues.append("audio=False still has LTXVSeparateAVLatent")
    cases["audio_false"] = {
        "leftover_audio_types": leftover,
        "create_video_audio": audio_off,
        "has_separate": "LTXVSeparateAVLatent" in types_off,
    }

    payload = {"ok": not issues, "issues": issues, "cases": cases}
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(payload, ensure_ascii=False, indent=2))
    return 0 if not issues else 1


if __name__ == "__main__":
    raise SystemExit(main())
