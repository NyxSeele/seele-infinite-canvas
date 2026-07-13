"""视频画质增强：从本地/URL 解析视频元数据（ffprobe / ffmpeg 回退）。"""

from __future__ import annotations

import json
import re
import shutil
import subprocess
import tempfile
from pathlib import Path
from typing import Any

import httpx
from fastapi import HTTPException
from sqlalchemy.orm import Session

from core.config import settings
from models import User
from services.media_access import resolve_video_source_for_enhance


def _ffmpeg_executable() -> str:
    try:
        import imageio_ffmpeg

        exe = imageio_ffmpeg.get_ffmpeg_exe()
        if exe and Path(exe).is_file():
            return exe
    except Exception:
        pass
    system = shutil.which("ffmpeg")
    if system:
        return system
    raise HTTPException(status_code=503, detail="ffmpeg 不可用，无法分析视频")


def _ffprobe_executable() -> str | None:
    try:
        ffmpeg = _ffmpeg_executable()
        candidate = Path(ffmpeg).with_name(
            "ffprobe.exe" if Path(ffmpeg).suffix else "ffprobe"
        )
        if candidate.is_file():
            return str(candidate)
    except HTTPException:
        pass
    # imageio bundle may only ship ffmpeg; fall back to system ffprobe
    return shutil.which("ffprobe")


def _parse_fps(value: str | float | int | None) -> float:
    if value is None:
        return 24.0
    if isinstance(value, (int, float)):
        return float(value) if float(value) > 0 else 24.0
    text = str(value).strip()
    if "/" in text:
        num, den = text.split("/", 1)
        try:
            den_f = float(den)
            return float(num) / den_f if den_f > 0 else 24.0
        except ValueError:
            return 24.0
    try:
        fps = float(text)
        return fps if fps > 0 else 24.0
    except ValueError:
        return 24.0


def _probe_with_ffprobe(video_path: Path) -> dict[str, Any] | None:
    ffprobe = _ffprobe_executable()
    if not ffprobe:
        return None
    try:
        result = subprocess.run(
            [
                ffprobe,
                "-v",
                "quiet",
                "-print_format",
                "json",
                "-show_streams",
                "-show_format",
                str(video_path),
            ],
            capture_output=True,
            text=True,
            timeout=30,
        )
    except (FileNotFoundError, subprocess.TimeoutExpired):
        return None
    if result.returncode != 0:
        return None
    try:
        payload = json.loads(result.stdout or "{}")
    except json.JSONDecodeError:
        return None
    streams = payload.get("streams") or []
    video_stream = next((s for s in streams if s.get("codec_type") == "video"), None)
    if not video_stream:
        return None
    fmt = payload.get("format") or {}
    duration = float(fmt.get("duration") or video_stream.get("duration") or 0)
    width = int(video_stream.get("width") or 0)
    height = int(video_stream.get("height") or 0)
    fps = _parse_fps(video_stream.get("avg_frame_rate") or video_stream.get("r_frame_rate"))
    if width <= 0 or height <= 0 or duration <= 0:
        return None
    return {
        "width": width,
        "height": height,
        "duration": round(duration, 3),
        "fps": round(fps, 3),
        "source_type": "ai_generated",
    }


def _probe_with_ffmpeg_stderr(video_path: Path) -> dict[str, Any]:
    ffmpeg = _ffmpeg_executable()
    try:
        result = subprocess.run(
            [ffmpeg, "-i", str(video_path)],
            capture_output=True,
            text=True,
            timeout=30,
        )
    except (FileNotFoundError, subprocess.TimeoutExpired) as exc:
        raise HTTPException(status_code=503, detail="无法读取视频信息") from exc
    stderr = result.stderr or ""
    dur_match = re.search(r"Duration:\s*(\d+):(\d+):(\d+(?:\.\d+)?)", stderr)
    if not dur_match:
        raise HTTPException(status_code=400, detail="无法解析视频时长")
    hours, minutes, seconds = dur_match.groups()
    duration = int(hours) * 3600 + int(minutes) * 60 + float(seconds)

    width, height = 0, 0
    fps = 24.0
    video_match = re.search(
        r"Video:.*?,\s*(\d+)x(\d+)(?:.*?,\s*([\d.]+)\s*fps)?",
        stderr,
        re.IGNORECASE,
    )
    if video_match:
        width = int(video_match.group(1))
        height = int(video_match.group(2))
        if video_match.group(3):
            fps = float(video_match.group(3))
    if width <= 0 or height <= 0:
        raise HTTPException(status_code=400, detail="无法解析视频分辨率")

    return {
        "width": width,
        "height": height,
        "duration": round(duration, 3),
        "fps": round(fps, 3),
        "source_type": "ai_generated",
    }


def probe_video_info(video_path: Path) -> dict[str, Any]:
    """从本地文件探测 width/height/duration/fps。"""
    if not video_path.is_file():
        raise HTTPException(status_code=404, detail="视频文件不存在")
    probed = _probe_with_ffprobe(video_path)
    if probed:
        return probed
    return _probe_with_ffmpeg_stderr(video_path)


async def _download_http_video(url: str) -> Path:
    timeout = float(settings.media_download_timeout)
    async with httpx.AsyncClient(timeout=timeout) as client:
        res = await client.get(url)
        res.raise_for_status()
        data = res.content
    tmp = tempfile.NamedTemporaryFile(delete=False, suffix=".mp4")
    try:
        tmp.write(data)
        tmp.close()
        return Path(tmp.name)
    except Exception:
        Path(tmp.name).unlink(missing_ok=True)
        raise


async def probe_video_info_from_url(db: Session, user: User, video_url: str) -> dict[str, Any]:
    """解析可访问视频并探测元数据；外部 http(s) 临时下载后探测。"""
    from services.media_access import normalize_media_reference_url

    raw = normalize_media_reference_url((video_url or "").strip())
    if not raw:
        raise HTTPException(status_code=400, detail="视频地址不能为空")

    temp_path: Path | None = None
    try:
        if raw.startswith("http://") or raw.startswith("https://"):
            temp_path = await _download_http_video(raw)
            return probe_video_info(temp_path)

        local_path = resolve_video_source_for_enhance(db, user, raw)
        if local_path is not None:
            return probe_video_info(local_path)

        raise HTTPException(status_code=400, detail="视频源无效或无权访问")
    finally:
        if temp_path is not None:
            temp_path.unlink(missing_ok=True)
