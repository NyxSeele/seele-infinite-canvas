#!/usr/bin/env python3
"""G33: 显式 camera_move / shot_scale 进入 Wan compile prompt。"""
from __future__ import annotations

import json
import sys
from pathlib import Path

BACKEND_ROOT = Path(__file__).resolve().parents[1]
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

from services.prompt_builder import build_prompt

OUT = Path("/root/autodl-tmp/logs/g33_video_style_picker.json")
SCENE = "rainy street, woman with umbrella"


def _case(name: str, **kwargs) -> dict:
    result = build_prompt(SCENE, model_target="wan-i2v", **kwargs)
    return {
        "name": name,
        "kwargs": kwargs,
        "positive_prompt": result.positive_prompt,
    }


def main() -> int:
    cases = [
        _case("push_in", camera_move="push_in", shot_scale="auto"),
        _case("auto_move", camera_move="auto", shot_scale="auto"),
        _case("medium", camera_move="auto", shot_scale="medium"),
        _case("auto_scale", camera_move="auto", shot_scale="auto"),
    ]
    issues: list[str] = []

    c0 = cases[0]["positive_prompt"].lower()
    if "push in" not in c0:
        issues.append(f"push_in missing: {cases[0]['positive_prompt'][:200]}")

    c1 = cases[1]["positive_prompt"].lower()
    for banned in ("push in", "pull out", "tracking shot", "static camera", "medium shot", "close-up"):
        if banned in c1:
            issues.append(f"auto_move unexpectedly contains {banned!r}")

    c2 = cases[2]["positive_prompt"].lower()
    if "medium shot" not in c2:
        issues.append(f"medium missing: {cases[2]['positive_prompt'][:200]}")

    c3 = cases[3]["positive_prompt"].lower()
    for banned in ("medium shot", "close-up", "wide shot", "full shot", "push in"):
        if banned in c3:
            issues.append(f"auto_scale unexpectedly contains {banned!r}")

    out = {"cases": cases, "issues": issues, "ok": not issues}
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(out, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(out, ensure_ascii=False, indent=2))
    print(f"Wrote {OUT}")
    return 0 if not issues else 1


if __name__ == "__main__":
    sys.exit(main())
