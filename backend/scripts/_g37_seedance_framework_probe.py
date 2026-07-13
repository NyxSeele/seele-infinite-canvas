#!/usr/bin/env python3
"""G37: Seedance framework probe (no live API call without key)."""
from __future__ import annotations

import json
import sys
from pathlib import Path

BACKEND_ROOT = Path(__file__).resolve().parents[1]
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

from model_registry import MODEL_MAP, resolve_video_backend
from providers.seedance import SeedanceClient
from services.prompt_builder import SEEDANCE_MAX_WORDS, SEEDANCE_MIN_WORDS, compress_for_seedance

OUT = Path("/root/autodl-tmp/logs/g37_seedance_framework_probe.json")

LONG = (
    "A highly detailed cinematic masterpiece of a young woman walking through a rainy neon street "
    "at night with intricate reflections on wet asphalt, ultra realistic lighting, best quality, "
    "8k, complex background crowds, shallow depth of field, film grain, volumetric fog, "
    "dramatic backlight, emotional expression, continuous tracking motion across the block"
)


def main() -> int:
    issues: list[str] = []

    entry = MODEL_MAP.get("seedance-2.0")
    if not entry:
        issues.append("MODEL_MAP missing seedance-2.0")
    else:
        if entry.get("type") != "api":
            issues.append(f"type={entry.get('type')!r}")
        if entry.get("video_backend") != "seedance":
            issues.append(f"video_backend={entry.get('video_backend')!r}")
        if entry.get("default_enabled"):
            issues.append("seedance-2.0 should be default_enabled=False without key")
        if resolve_video_backend("seedance-2.0") != "seedance":
            issues.append("resolve_video_backend failed")

    result = compress_for_seedance(LONG, camera_move="push_in", shot_scale="medium")
    words = result.positive_prompt.split()
    n = len(words)
    if n < SEEDANCE_MIN_WORDS or n > SEEDANCE_MAX_WORDS:
        issues.append(f"word_count={n} not in [{SEEDANCE_MIN_WORDS},{SEEDANCE_MAX_WORDS}]")
    if "push in" not in result.positive_prompt.lower():
        issues.append("missing push in")
    if "medium shot" not in result.positive_prompt.lower():
        issues.append("missing medium shot")

    client = SeedanceClient(api_key="")
    if client.is_configured():
        issues.append("empty key should not be configured")
    # init with missing key must not raise
    try:
        SeedanceClient()
    except Exception as e:
        issues.append(f"client init raised: {e}")

    out = {
        "ok": not issues,
        "issues": issues,
        "word_count": n,
        "positive_prompt": result.positive_prompt,
        "configured": SeedanceClient().is_configured(),
    }
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(out, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(out, ensure_ascii=False, indent=2))
    print(f"Wrote {OUT}")
    return 0 if not issues else 1


if __name__ == "__main__":
    sys.exit(main())
