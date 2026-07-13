#!/usr/bin/env python3
"""G36: VideoGenerationNode card-level CameraMotionPicker defaults."""
from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
OUT = Path("/root/autodl-tmp/logs/g36_card_style_picker.json")
NODE = ROOT / "frontend/src/components/canvas/VideoGenerationNode.jsx"
PICKER = ROOT / "frontend/src/components/canvas/CameraMotionPicker.jsx"


def main() -> int:
    issues: list[str] = []
    src = NODE.read_text(encoding="utf-8")
    picker = PICKER.read_text(encoding="utf-8")

    if "CameraMotionPicker" not in src:
        issues.append("VideoGenerationNode missing CameraMotionPicker import/usage")
    if "cameraMove" not in src or "shotScale" not in src:
        issues.append("VideoGenerationNode missing cameraMove/shotScale fields")
    if 'data.cameraMove || "auto"' not in src and 'cameraMove = data.cameraMove || "auto"' not in src:
        # accept either pattern
        if 'cameraMove || "auto"' not in src:
            issues.append("default cameraMove auto not found")
    if 'shotScale || "auto"' not in src and 'data.shotScale || "auto"' not in src:
        issues.append("default shotScale auto not found")
    if "gn2-camera-summary" not in src:
        issues.append("collapsed summary control missing")
    if "GenerationCardNode" in src and "image-gen only" in src:
        pass
    if 'id: "auto"' not in picker:
        issues.append("CameraMotionPicker missing auto option")

    # GenerationCardNode must NOT be the video host
    card = (ROOT / "frontend/src/components/canvas/GenerationCardNode.jsx").read_text(encoding="utf-8")
    if "CameraMotionPicker" in card:
        issues.append("CameraMotionPicker incorrectly mounted on GenerationCardNode")

    out = {"ok": not issues, "issues": issues, "node": str(NODE)}
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(out, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(out, ensure_ascii=False, indent=2))
    print(f"Wrote {OUT}")
    return 0 if not issues else 1


if __name__ == "__main__":
    sys.exit(main())
