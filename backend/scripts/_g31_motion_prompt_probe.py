#!/usr/bin/env python3
"""G31: 运镜字段进入 Wan compile prompt；可选 quality steps 结构检查。"""
from __future__ import annotations

import json
import sys
from pathlib import Path

BACKEND_ROOT = Path(__file__).resolve().parents[1]
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

from comfyui.client import build_wan_i2v_workflow, resolve_wan_steps
from services.prompt_builder import build_prompt, prepend_wan_motion_english

OUT = Path("/root/autodl-tmp/logs/g31_motion_prompt.json")


def main() -> int:
    scene = "雨中街道，女子撑伞走入；运镜：缓慢推近；景别：中景"
    prepended = prepend_wan_motion_english(scene)
    compiled = build_prompt(scene, model_target="wan-i2v")
    pos = compiled.positive_prompt.lower()
    issues: list[str] = []
    if "dollies in" not in pos and "dolly" not in pos:
        issues.append(f"missing dolly in positive: {compiled.positive_prompt[:200]}")
    if "medium shot" not in pos:
        issues.append(f"missing medium shot: {compiled.positive_prompt[:200]}")
    if "运镜" in compiled.positive_prompt:
        issues.append("Chinese 运镜 label should be stripped from Wan positive")

    steps_q = resolve_wan_steps("quality")
    wf = build_wan_i2v_workflow(
        compiled.positive_prompt,
        compiled.negative_prompt or "low quality",
        "probe_ref.png",
        duration_sec=3,
        seed=1,
        steps=steps_q,
    )
    high = next(
        n
        for n in wf.values()
        if n.get("class_type") == "KSamplerAdvanced"
        and n["inputs"].get("add_noise") == "enable"
    )
    if high["inputs"]["steps"] != 8 or high["inputs"]["end_at_step"] != 4:
        issues.append(f"quality sampler split unexpected: {high['inputs']}")

    out = {
        "scene": scene,
        "prepended": prepended,
        "positive_prompt": compiled.positive_prompt,
        "steps_quality": steps_q,
        "issues": issues,
        "ok": not issues,
    }
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(out, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(out, ensure_ascii=False, indent=2))
    print(f"Wrote {OUT}")
    return 0 if not issues else 1


if __name__ == "__main__":
    sys.exit(main())
