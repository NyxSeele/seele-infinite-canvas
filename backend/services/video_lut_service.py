"""视频 LUT 后处理（ffmpeg lut3d）。"""

from __future__ import annotations

import logging
import subprocess
import uuid
from pathlib import Path

from fastapi import HTTPException

from services.lut_registry import resolve_builtin_lut_path
from services.video_enhance_probe import _ffmpeg_executable

logger = logging.getLogger(__name__)

UPLOADS_LUTS = Path(__file__).resolve().parent.parent / "uploads" / "luts"
UPLOADS_VIDEOS = Path(__file__).resolve().parent.parent / "uploads" / "videos"


def _quote_ffmpeg_path(path: Path) -> str:
    s = str(path.resolve()).replace("\\", "/")
    if ":" in s and "/" in s:
        return s.replace(":", "\\:", 1)
    return s


def resolve_custom_lut_path(custom_url: str | None) -> Path | None:
    from services.media_access import ref_url_to_rel_path, resolve_upload_file_path

    url = (custom_url or "").strip()
    if not url:
        return None
    rel = ref_url_to_rel_path(url)
    if not rel or not rel.startswith("luts/"):
        return None
    path = resolve_upload_file_path(rel)
    if not path.is_file():
        return None
    if path.suffix.lower() != ".cube":
        raise HTTPException(status_code=400, detail="LUT 文件须为 .cube 格式")
    return path


def resolve_lut_file_path(
    *,
    lut_preset: str | None,
    lut_custom_url: str | None,
) -> Path | None:
    custom = resolve_custom_lut_path(lut_custom_url)
    if custom:
        return custom
    return resolve_builtin_lut_path(lut_preset)


def apply_lut_to_video_file(
    input_path: Path,
    lut_path: Path,
    output_path: Path,
    *,
    timeout_sec: int = 600,
) -> None:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    lut_filter = f"lut3d=file='{_quote_ffmpeg_path(lut_path)}'"
    cmd = [
        _ffmpeg_executable(),
        "-y",
        "-i",
        str(input_path),
        "-vf",
        lut_filter,
        "-c:v",
        "libx264",
        "-crf",
        "18",
        "-preset",
        "medium",
        "-c:a",
        "copy",
        "-movflags",
        "+faststart",
        str(output_path),
    ]
    try:
        proc = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=timeout_sec,
            check=False,
        )
    except subprocess.TimeoutExpired as exc:
        raise HTTPException(status_code=504, detail="LUT 处理超时") from exc
    if proc.returncode != 0:
        logger.error("ffmpeg lut failed: %s", proc.stderr[-2000:])
        raise HTTPException(status_code=500, detail="LUT 处理失败")
    if not output_path.is_file() or output_path.stat().st_size == 0:
        raise HTTPException(status_code=500, detail="LUT 输出文件无效")


def new_lut_output_path() -> Path:
    UPLOADS_VIDEOS.mkdir(parents=True, exist_ok=True)
    return UPLOADS_VIDEOS / f"{uuid.uuid4().hex}.mp4"
