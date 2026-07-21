#!/usr/bin/env python3
"""Probe short-video factory with mock LLM + mock TTS + mock stock (no GPU / no network)."""

from __future__ import annotations

import asyncio
import json
import os
import subprocess
import sys
import uuid
from pathlib import Path
from unittest.mock import patch

BACKEND_ROOT = Path(__file__).resolve().parents[1]
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

os.environ.setdefault("SHORT_VIDEO_MOCK_LLM", "1")
os.environ.setdefault("SHORT_VIDEO_MOCK_TTS", "1")
os.environ.setdefault("SHORT_VIDEO_MOCK_STOCK", "1")

from services.short_video_factory import (  # noqa: E402
    build_factory_video,
    build_timeline_cues,
    generate_segments,
    synthesize_segments_audio,
    task_output_dir,
)


def _fake_ffmpeg_run(cmd, check=True, capture_output=True, text=True):
    output = Path(cmd[-1])
    if output.suffix == ".mp4":
        if "concat" in cmd:
            output.write_bytes(b"final-mp4")
        else:
            output.write_bytes(b"segment-mp4")
    return subprocess.CompletedProcess(cmd, 0, "", "")


async def main() -> None:
    task_id = str(uuid.uuid4())
    topic = os.environ.get("SHORT_VIDEO_PROBE_TOPIC", "Velora 探针短视频")
    visual_source = os.environ.get("SHORT_VIDEO_PROBE_VISUAL", "slide")
    segments = await generate_segments(topic, segment_count=2)
    task_dir = task_output_dir(task_id)
    segments = await synthesize_segments_audio(
        segments,
        task_dir=task_dir,
        voice_name="zh-CN-XiaoxiaoNeural",
    )
    cues = build_timeline_cues(segments)
    durations = [seg.duration_sec for seg in segments]
    with patch.object(subprocess, "run", side_effect=_fake_ffmpeg_run):
        final_path = await build_factory_video(
            segments,
            task_dir=task_dir,
            width=640,
            height=360,
            enable_tts=True,
            visual_source=visual_source,
            aspect="9:16",
        )
    payload = {
        "task_id": task_id,
        "final": str(final_path),
        "visual_source": visual_source,
        "durations": durations,
        "cues": cues,
        "non_uniform": cues[1]["start"] != 2.0 if len(cues) > 1 else True,
    }
    print(f"PROBE_OK {json.dumps(payload, ensure_ascii=False)}")


if __name__ == "__main__":
    asyncio.run(main())
