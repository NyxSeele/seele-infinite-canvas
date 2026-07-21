"""Post-process short-video outputs: subtitles and optional BGM."""

from __future__ import annotations

import asyncio
import logging
import shutil
import subprocess
from pathlib import Path
from typing import Any

import yaml

from services.audio_mix import mix_sfx_into_video
from services.video_enhance_probe import _ffmpeg_executable

logger = logging.getLogger(__name__)

TEMPLATE_DIR = Path(__file__).resolve().parents[1] / "short_video_templates"
PROJECT_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_BGM_PATH = PROJECT_ROOT / "data" / "short_video" / "bgm" / "default.mp3"


def load_template(name: str = "portrait_default") -> dict[str, Any]:
    path = TEMPLATE_DIR / f"{name}.yaml"
    if not path.is_file():
        return {
            "subtitle": {"font_size": 42, "margin_bottom": 120, "font_color": "white"},
            "bgm_volume": 0.25,
        }
    return yaml.safe_load(path.read_text(encoding="utf-8")) or {}


def _escape_drawtext(text: str) -> str:
    escaped = text.replace("\\", "\\\\").replace(":", "\\:").replace("'", "\\'")
    return escaped.replace("\n", " ")


def _subtitle_fontfile() -> str | None:
    for candidate in (
        "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
        "/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc",
    ):
        if Path(candidate).is_file():
            return candidate
    return None


def _ffmpeg_has_filter(ffmpeg: str, name: str) -> bool:
    try:
        proc = subprocess.run(
            [ffmpeg, "-hide_banner", "-filters"],
            check=False,
            capture_output=True,
            text=True,
            timeout=15,
        )
    except Exception:
        return False
    blob = f"{proc.stdout or ''}\n{proc.stderr or ''}"
    # e.g. " T.C drawtext          V->V       Draw text..."
    return any(
        line.split() and len(line.split()) >= 2 and line.split()[1] == name
        for line in blob.splitlines()
    )


def _ffmpeg_for_subtitles() -> str:
    """Prefer a build with libfreetype drawtext; imageio_ffmpeg often ships without it."""
    candidates: list[str] = []
    system = shutil.which("ffmpeg")
    if system:
        candidates.append(system)
    try:
        bundled = _ffmpeg_executable()
        if bundled and bundled not in candidates:
            candidates.append(bundled)
    except Exception:
        pass
    for exe in candidates:
        if _ffmpeg_has_filter(exe, "drawtext"):
            return exe
    if candidates:
        return candidates[0]
    raise RuntimeError("ffmpeg 不可用，无法烧录字幕")


def burn_subtitles(
    video_path: Path,
    cues: list[dict[str, Any]],
    output_path: Path,
    *,
    template_name: str = "portrait_default",
) -> Path:
    active = [cue for cue in cues if str(cue.get("text") or "").strip()]
    if not active:
        shutil.copy2(video_path, output_path)
        return output_path
    template = load_template(template_name)
    subtitle_cfg = template.get("subtitle") or {}
    font_size = int(subtitle_cfg.get("font_size", 42))
    margin_bottom = int(subtitle_cfg.get("margin_bottom", 120))
    font_color = str(subtitle_cfg.get("font_color", "white"))
    filters: list[str] = []
    for cue in active:
        text = _escape_drawtext(str(cue.get("text") or "").strip())
        start = float(cue.get("start", 0))
        end = float(cue.get("end", start + 2))
        draw = (
            f"drawtext=text='{text}':fontsize={font_size}:fontcolor={font_color}:"
            f"x=(w-text_w)/2:y=h-{margin_bottom}:enable='between(t,{start},{end})'"
        )
        fontfile = _subtitle_fontfile()
        if fontfile:
            draw += f":fontfile='{fontfile}'"
        filters.append(draw)
    ffmpeg = _ffmpeg_for_subtitles()
    cmd = [
        ffmpeg,
        "-y",
        "-i",
        str(video_path),
        "-vf",
        ",".join(filters),
        "-c:v",
        "libx264",
        "-pix_fmt",
        "yuv420p",
        "-an",
        str(output_path),
    ]
    subprocess.run(cmd, check=True, capture_output=True, text=True)
    return output_path


def mix_bgm(
    video_path: Path,
    bgm_path: Path,
    output_path: Path,
    *,
    volume: float = 0.25,
) -> Path:
    if not bgm_path.is_file():
        logger.info("BGM file missing, skip mix: %s", bgm_path)
        shutil.copy2(video_path, output_path)
        return output_path
    return mix_sfx_into_video(video_path, bgm_path, output_path, volume=volume)


def resolve_bgm_path(bgm: str) -> Path | None:
    token = (bgm or "none").strip().lower()
    if token in ("", "none", "skip"):
        return None
    if token == "default":
        return DEFAULT_BGM_PATH if DEFAULT_BGM_PATH.is_file() else None
    candidate = Path(token)
    return candidate if candidate.is_file() else None


def apply_short_video_postprocess(
    video_path: Path,
    *,
    task_dir: Path,
    cues: list[dict[str, Any]],
    bgm: str = "none",
    aspect: str = "9:16",
    burn_captions: bool = True,
) -> Path:
    template_name = "portrait_default" if aspect != "16:9" else "landscape_default"
    template = load_template(template_name)
    current = video_path
    if burn_captions and cues:
        captioned = task_dir / "final_captioned.mp4"
        current = burn_subtitles(current, cues, captioned, template_name=template_name)
    bgm_path = resolve_bgm_path(bgm)
    if bgm_path is None:
        return current
    mixed = task_dir / "final_with_bgm.mp4"
    return mix_bgm(current, bgm_path, mixed, volume=float(template.get("bgm_volume", 0.25)))


def should_schedule_video_postprocess(task) -> bool:
    if not task or task.task_type != "video" or task.status != "completed":
        return False
    if bool(getattr(task, "use_reactor", False)):
        return True
    if not (task.sound_note or "").strip():
        return False
    return (task.video_backend or "").strip().lower() != "ltx2"


def schedule_video_postprocess(task) -> None:
    """G45 逐帧换脸（若 use_reactor）→ 链式 G39 sound_note；仅 sound_note 时直接混音。"""
    if not should_schedule_video_postprocess(task):
        return
    if bool(getattr(task, "use_reactor", False)):
        from services.reactor_video import maybe_apply_reactor_video

        asyncio.create_task(maybe_apply_reactor_video(task.id))
        return
    from services.audiogen_postprocess import maybe_apply_sound_note_mix

    asyncio.create_task(maybe_apply_sound_note_mix(task.id))
