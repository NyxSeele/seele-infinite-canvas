"""G39: 将 wav 音效混入 mp4（ffmpeg）。"""

from __future__ import annotations

import logging
import subprocess
import uuid
from pathlib import Path

from services.video_enhance_probe import _ffmpeg_executable

logger = logging.getLogger(__name__)

UPLOADS_VIDEOS = Path(__file__).resolve().parent.parent / "uploads" / "videos"


def mix_sfx_into_video(
    video_path: Path,
    wav_path: Path,
    output_path: Path | None = None,
    *,
    volume: float = 0.85,
    timeout_sec: int = 300,
) -> Path:
    """
    将音效混入视频。若原片已有音轨则 amix；否则仅挂载音效。
    使用 -shortest，音量可控。输出默认旁路 *_sfx.mp4。
    """
    video_path = Path(video_path)
    wav_path = Path(wav_path)
    if not video_path.is_file():
        raise FileNotFoundError(f"视频不存在: {video_path}")
    if not wav_path.is_file():
        raise FileNotFoundError(f"音效不存在: {wav_path}")

    if output_path is None:
        UPLOADS_VIDEOS.mkdir(parents=True, exist_ok=True)
        stem = video_path.stem
        output_path = UPLOADS_VIDEOS / f"{stem}_sfx_{uuid.uuid4().hex[:8]}.mp4"
    else:
        output_path = Path(output_path)
        output_path.parent.mkdir(parents=True, exist_ok=True)

    vol = max(0.05, min(float(volume), 2.0))
    ffmpeg = _ffmpeg_executable()

    # 通用：视频 copy + 音效作为唯一/混合音轨；-shortest 对齐较短轨
    # 若原视频无音轨，filter 仍可用 anullsrc 兜底较复杂；用 -map 0:v -map 1:a 更稳
    has_audio = _video_has_audio(video_path)
    if has_audio:
        filter_complex = (
            f"[1:a]volume={vol}[sfx];"
            f"[0:a][sfx]amix=inputs=2:duration=shortest:dropout_transition=0[aout]"
        )
        cmd = [
            ffmpeg,
            "-y",
            "-i",
            str(video_path),
            "-i",
            str(wav_path),
            "-filter_complex",
            filter_complex,
            "-map",
            "0:v:0",
            "-map",
            "[aout]",
            "-c:v",
            "copy",
            "-c:a",
            "aac",
            "-b:a",
            "192k",
            "-shortest",
            "-movflags",
            "+faststart",
            str(output_path),
        ]
    else:
        cmd = [
            ffmpeg,
            "-y",
            "-i",
            str(video_path),
            "-i",
            str(wav_path),
            "-filter:a:1",
            f"volume={vol}",
            "-map",
            "0:v:0",
            "-map",
            "1:a:0",
            "-c:v",
            "copy",
            "-c:a",
            "aac",
            "-b:a",
            "192k",
            "-shortest",
            "-movflags",
            "+faststart",
            str(output_path),
        ]

    proc = subprocess.run(
        cmd,
        capture_output=True,
        text=True,
        timeout=timeout_sec,
    )
    if proc.returncode != 0 or not output_path.is_file():
        logger.error("ffmpeg mix failed: %s", (proc.stderr or "")[-2000:])
        raise RuntimeError(f"ffmpeg 混音失败: {(proc.stderr or '')[-400:]}")
    return output_path


def _video_has_audio(video_path: Path) -> bool:
    ffmpeg = _ffmpeg_executable()
    try:
        proc = subprocess.run(
            [ffmpeg, "-i", str(video_path)],
            capture_output=True,
            text=True,
            timeout=30,
        )
    except Exception:
        return False
    text = (proc.stderr or "") + (proc.stdout or "")
    return "Audio:" in text
