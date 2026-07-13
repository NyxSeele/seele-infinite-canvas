#!/usr/bin/env python3
"""G39: AudioGen 译英 + 生成探针（可跳过：无权重 / 无 GPU 依赖）。"""
from __future__ import annotations

import asyncio
import json
import sys
import wave
from pathlib import Path

BACKEND_ROOT = Path(__file__).resolve().parents[1]
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

OUT = Path("/root/autodl-tmp/logs/g39_audiogen_probe.json")
DURATION = 2.0
TOLERANCE = 0.75


def _wav_duration(path: Path) -> float:
    with wave.open(str(path), "rb") as wf:
        return wf.getnframes() / float(wf.getframerate())


async def _translate(zh: str) -> tuple[str, str | None]:
    from comfyui import llm

    result = await llm.translate_to_english(zh, mode="video")
    return (result.get("positive") or zh).strip(), result.get("error")


def main() -> int:
    from services.audiogen import audiogen_available, generate_sfx_wav

    issues: list[str] = []
    payload: dict = {"ok": False, "skipped": False}

    if not audiogen_available():
        payload.update(
            {
                "ok": True,
                "skipped": True,
                "reason": "AudioGen weights missing",
            }
        )
        OUT.parent.mkdir(parents=True, exist_ok=True)
        OUT.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
        print(json.dumps(payload, ensure_ascii=False, indent=2))
        return 0

    try:
        from audiocraft.models import AudioGen  # noqa: F401
    except Exception as exc:
        payload.update(
            {
                "ok": True,
                "skipped": True,
                "reason": f"audiocraft import failed: {exc}",
            }
        )
        OUT.parent.mkdir(parents=True, exist_ok=True)
        OUT.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
        print(json.dumps(payload, ensure_ascii=False, indent=2))
        return 0

    zh = "雨打屋檐的环境音"
    en, terr = asyncio.run(_translate(zh))
    payload["prompt_zh"] = zh
    payload["prompt_en"] = en
    payload["translate_error"] = terr

    try:
        wav = generate_sfx_wav(en or "rain on rooftop", duration=DURATION)
        dur = _wav_duration(wav)
        payload["wav"] = str(wav)
        payload["duration"] = dur
        if abs(dur - DURATION) > TOLERANCE:
            issues.append(f"duration {dur:.2f} not in {DURATION}±{TOLERANCE}")
        if not wav.is_file() or wav.stat().st_size < 1000:
            issues.append("wav missing or too small")
    except Exception as exc:
        issues.append(f"generate failed: {exc}")

    payload["ok"] = not issues
    payload["issues"] = issues
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(payload, ensure_ascii=False, indent=2))
    return 0 if not issues else 1


if __name__ == "__main__":
    raise SystemExit(main())
