#!/usr/bin/env python3
"""G45: 视频逐帧 ReActor 探针 — 短视频拆帧→换脸→合帧，并确认 tmp 清理。"""
from __future__ import annotations

import asyncio
import json
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
sys.path.insert(0, str(Path(__file__).resolve().parent))

from services.reactor_video import (
    cleanup_tmp_reactor,
    swap_faces_in_video,
    tmp_reactor_dir,
    _ffmpeg_bin,
)
from providers.comfyui import build_reactor_frame_workflow

OUT = Path("/root/autodl-tmp/logs/g45_reactor_video_probe.json")
BACKEND = Path(__file__).resolve().parents[1]
FACE = BACKEND / "uploads" / "images" / "mock-cast-ref.jpg"
SHORT_MP4 = Path("/tmp/g45_probe_short.mp4")
SWAPPED = Path("/tmp/g45_probe_swapped.mp4")
TASK_ID = "g45-probe-local"


def _ensure_face() -> Path:
    if FACE.is_file():
        return FACE
    from generate_mock_assets import main as gen

    gen()
    if not FACE.is_file():
        raise FileNotFoundError(FACE)
    return FACE


def _make_short_video(path: Path, *, seconds: float = 3.0) -> Path:
    ffmpeg = _ffmpeg_bin()
    path.parent.mkdir(parents=True, exist_ok=True)
    # 用正脸图作静态帧源，保证画面有脸可换
    face = _ensure_face()
    cmd = [
        ffmpeg,
        "-y",
        "-loop",
        "1",
        "-i",
        str(face),
        "-f",
        "lavfi",
        "-i",
        "anullsrc=r=44100:cl=stereo",
        "-t",
        str(seconds),
        "-r",
        "8",
        "-c:v",
        "libx264",
        "-pix_fmt",
        "yuv420p",
        "-c:a",
        "aac",
        "-shortest",
        str(path),
    ]
    subprocess.run(cmd, check=True, capture_output=True, timeout=120)
    return path


def _has_video_stream(path: Path) -> bool:
    ffmpeg = _ffmpeg_bin()
    proc = subprocess.run(
        [ffmpeg, "-i", str(path)],
        capture_output=True,
        text=True,
        timeout=30,
    )
    text = (proc.stderr or "") + (proc.stdout or "")
    return "Video:" in text or "Video：" in text


def main() -> int:
    report: dict = {"ok": False, "cases": {}}
    issues: list[str] = []

    # 结构
    wf = build_reactor_frame_workflow(frame_filename="a.png", face_filename="b.png")
    report["cases"]["workflow"] = {
        "has_reactor": wf.get("60", {}).get("class_type") == "ReActorFaceSwap",
        "no_pulid": "Nunchaku" not in json.dumps(wf),
    }
    if not report["cases"]["workflow"]["has_reactor"]:
        issues.append("workflow missing ReActorFaceSwap")

    cleanup_tmp_reactor(TASK_ID)
    try:
        _make_short_video(SHORT_MP4, seconds=3.0)
        face = _ensure_face()
        SWAPPED.unlink(missing_ok=True)

        out = asyncio.run(
            swap_faces_in_video(
                SHORT_MP4,
                face,
                SWAPPED,
                task_id=TASK_ID,
                max_frames=16,  # 3s@8fps≈24；限 16 控盘/时
            )
        )
        tmp_left = tmp_reactor_dir(TASK_ID).exists()
        has_v = out.is_file() and _has_video_stream(out)
        report["cases"]["pipeline"] = {
            "output": str(out),
            "output_exists": out.is_file(),
            "output_bytes": out.stat().st_size if out.is_file() else 0,
            "has_video_stream": has_v,
            "tmp_cleaned": not tmp_left,
        }
        if not out.is_file():
            issues.append("swapped mp4 missing")
        if not has_v:
            issues.append("swapped mp4 has no video stream")
        if tmp_left:
            issues.append(f"tmp not cleaned: {tmp_reactor_dir(TASK_ID)}")
            cleanup_tmp_reactor(TASK_ID)
    except Exception as exc:
        issues.append(f"pipeline error: {exc}")
        report["cases"]["pipeline"] = {"error": str(exc)}
        cleanup_tmp_reactor(TASK_ID)

    report["ok"] = not issues
    report["issues"] = issues
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0 if report["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
