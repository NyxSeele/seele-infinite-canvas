"""Short-video factory MVP: topic -> slide segments -> ffmpeg concat."""

from __future__ import annotations

import json
import logging
import os
import re
import subprocess
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from PIL import Image, ImageDraw, ImageFont

from services.video_enhance_probe import _ffmpeg_executable

logger = logging.getLogger(__name__)

PROJECT_ROOT = Path(__file__).resolve().parents[2]
OUTPUT_ROOT = PROJECT_ROOT / "data" / "short_video"
DEFAULT_SEGMENT_SECONDS = 2.0
DEFAULT_TEXT_MODEL = os.environ.get("SHORT_VIDEO_TEXT_MODEL", "qwen-turbo")
DEFAULT_VOICE_NAME = "zh-CN-XiaoxiaoNeural"


@dataclass
class ShortVideoSegment:
    narration: str
    visual_prompt: str
    audio_path: str | None = None
    duration_sec: float | None = None
    cues: list[dict[str, Any]] = field(default_factory=list)


def aspect_to_size(aspect: str) -> tuple[int, int]:
    normalized = (aspect or "9:16").strip()
    if normalized in ("16:9", "landscape"):
        return 1920, 1080
    if normalized in ("1:1", "square"):
        return 1080, 1080
    return 1080, 1920


def task_output_dir(task_id: str) -> Path:
    path = OUTPUT_ROOT / task_id
    path.mkdir(parents=True, exist_ok=True)
    return path


def _mock_segments(topic: str, segment_count: int) -> list[ShortVideoSegment]:
    topic = (topic or "短视频").strip() or "短视频"
    return [
        ShortVideoSegment(
            narration=f"{topic} · 第{i + 1}段",
            visual_prompt=f"slide about {topic} part {i + 1}",
        )
        for i in range(max(1, segment_count))
    ]


def _parse_segments_payload(raw: str, topic: str, segment_count: int) -> list[ShortVideoSegment]:
    text = (raw or "").strip()
    if not text:
        return _mock_segments(topic, segment_count)
    match = re.search(r"\[.*\]", text, flags=re.DOTALL)
    payload = json.loads(match.group(0) if match else text)
    if not isinstance(payload, list):
        raise ValueError("LLM 返回的段落不是 JSON 数组")
    segments: list[ShortVideoSegment] = []
    for item in payload[: max(1, segment_count)]:
        if not isinstance(item, dict):
            continue
        narration = str(item.get("narration") or item.get("text") or "").strip()
        visual_prompt = str(item.get("visual_prompt") or item.get("prompt") or narration).strip()
        if narration:
            segments.append(ShortVideoSegment(narration=narration, visual_prompt=visual_prompt))
    if not segments:
        return _mock_segments(topic, segment_count)
    return segments


async def generate_segments(topic: str, segment_count: int = 3) -> list[ShortVideoSegment]:
    topic = (topic or "").strip()
    if not topic:
        raise ValueError("topic 不能为空")
    if os.environ.get("SHORT_VIDEO_MOCK_LLM", "").strip() in ("1", "true", "yes"):
        return _mock_segments(topic, segment_count)

    from providers.qwen import call_openai_compatible

    prompt = (
        f"你是短视频脚本助手。把主题拆成 {segment_count} 段旁白，每段 1-2 句中文。\n"
        f"主题：{topic}\n"
        "只输出 JSON 数组，每项字段：narration, visual_prompt。"
    )
    raw = await call_openai_compatible(DEFAULT_TEXT_MODEL, prompt, max_tokens=1200)
    return _parse_segments_payload(raw, topic, segment_count)


async def synthesize_segments_audio(
    segments: list[ShortVideoSegment],
    *,
    task_dir: Path,
    voice_name: str = DEFAULT_VOICE_NAME,
) -> list[ShortVideoSegment]:
    from services.edge_tts_service import synthesize_segment

    updated: list[ShortVideoSegment] = []
    for index, segment in enumerate(segments):
        audio_path = task_dir / f"audio_{index:02d}.mp3"
        result = await synthesize_segment(
            segment.narration,
            output_path=audio_path,
            voice=voice_name,
        )
        updated.append(
            ShortVideoSegment(
                narration=segment.narration,
                visual_prompt=segment.visual_prompt,
                audio_path=result["audio_path"],
                duration_sec=float(result["duration_sec"]),
                cues=list(result.get("cues") or []),
            )
        )
    return updated


def build_timeline_cues(
    segments: list[ShortVideoSegment],
    *,
    segment_seconds: float = DEFAULT_SEGMENT_SECONDS,
) -> list[dict[str, Any]]:
    """Build global subtitle cues by accumulating per-segment TTS timelines."""
    timeline: list[dict[str, Any]] = []
    offset = 0.0
    for segment in segments:
        duration = float(segment.duration_sec or segment_seconds)
        seg_cues = segment.cues or []
        if seg_cues:
            for cue in seg_cues:
                text = str(cue.get("text") or "").strip()
                if not text:
                    continue
                timeline.append(
                    {
                        "text": text,
                        "start": offset + float(cue.get("start", 0.0)),
                        "end": offset + float(cue.get("end", duration)),
                    }
                )
        else:
            narration = (segment.narration or "").strip()
            if narration:
                timeline.append(
                    {
                        "text": narration,
                        "start": offset,
                        "end": offset + duration,
                    }
                )
        offset += duration
    return timeline


def build_uniform_cues(
    segments: list[ShortVideoSegment],
    *,
    segment_seconds: float = DEFAULT_SEGMENT_SECONDS,
) -> list[dict[str, Any]]:
    return [
        {
            "text": seg.narration,
            "start": i * segment_seconds,
            "end": (i + 1) * segment_seconds,
        }
        for i, seg in enumerate(segments)
    ]


def _pick_font(size: int) -> ImageFont.ImageFont:
    for candidate in (
        "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
        "/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc",
    ):
        if Path(candidate).is_file():
            try:
                return ImageFont.truetype(candidate, size=size)
            except OSError:
                continue
    return ImageFont.load_default()


def render_slide_image(
    text: str,
    *,
    width: int,
    height: int,
    output_path: Path,
    bg_color: tuple[int, int, int] = (24, 32, 48),
) -> Path:
    image = Image.new("RGB", (width, height), color=bg_color)
    draw = ImageDraw.Draw(image)
    font = _pick_font(max(28, width // 28))
    wrapped = []
    line = ""
    for ch in text:
        trial = line + ch
        bbox = draw.textbbox((0, 0), trial, font=font)
        if bbox[2] - bbox[0] > width - 120:
            wrapped.append(line)
            line = ch
        else:
            line = trial
    if line:
        wrapped.append(line)
    y = height // 2 - (len(wrapped) * (font.size + 8)) // 2
    for row in wrapped:
        bbox = draw.textbbox((0, 0), row, font=font)
        x = (width - (bbox[2] - bbox[0])) // 2
        draw.text((x, y), row, fill=(240, 244, 255), font=font)
        y += font.size + 8
    output_path.parent.mkdir(parents=True, exist_ok=True)
    image.save(output_path)
    return output_path


def image_to_segment_mp4(
    image_path: Path,
    output_path: Path,
    *,
    duration_sec: float = DEFAULT_SEGMENT_SECONDS,
    width: int,
    height: int,
    audio_path: Path | None = None,
) -> Path:
    ffmpeg = _ffmpeg_executable()
    if audio_path is not None:
        cmd = [
            ffmpeg,
            "-y",
            "-loop",
            "1",
            "-i",
            str(image_path),
            "-i",
            str(audio_path),
            "-t",
            str(duration_sec),
            "-vf",
            f"scale={width}:{height}",
            "-c:v",
            "libx264",
            "-pix_fmt",
            "yuv420p",
            "-r",
            "24",
            "-c:a",
            "aac",
            "-shortest",
            str(output_path),
        ]
    else:
        cmd = [
            ffmpeg,
            "-y",
            "-loop",
            "1",
            "-i",
            str(image_path),
            "-t",
            str(duration_sec),
            "-vf",
            f"scale={width}:{height}",
            "-c:v",
            "libx264",
            "-pix_fmt",
            "yuv420p",
            "-r",
            "24",
            str(output_path),
        ]
    subprocess.run(cmd, check=True, capture_output=True, text=True)
    return output_path


def concat_segments(segment_paths: list[Path], output_path: Path) -> Path:
    if not segment_paths:
        raise ValueError("没有可合成的视频片段")
    output_path.parent.mkdir(parents=True, exist_ok=True)
    list_file = output_path.with_suffix(".txt")
    lines = [f"file '{path.resolve().as_posix()}'" for path in segment_paths]
    list_file.write_text("\n".join(lines) + "\n", encoding="utf-8")
    ffmpeg = _ffmpeg_executable()
    cmd = [
        ffmpeg,
        "-y",
        "-f",
        "concat",
        "-safe",
        "0",
        "-i",
        str(list_file),
        "-c",
        "copy",
        str(output_path),
    ]
    subprocess.run(cmd, check=True, capture_output=True, text=True)
    return output_path


def stock_to_segment_mp4(
    video_path: Path,
    output_path: Path,
    *,
    duration_sec: float,
    width: int,
    height: int,
    audio_path: Path | None = None,
) -> Path:
    ffmpeg = _ffmpeg_executable()
    vf = f"scale={width}:{height}:force_original_aspect_ratio=increase,crop={width}:{height}"
    if audio_path is not None and audio_path.is_file():
        cmd = [
            ffmpeg,
            "-y",
            "-stream_loop",
            "-1",
            "-i",
            str(video_path),
            "-i",
            str(audio_path),
            "-t",
            str(duration_sec),
            "-vf",
            vf,
            "-c:v",
            "libx264",
            "-pix_fmt",
            "yuv420p",
            "-r",
            "24",
            "-c:a",
            "aac",
            "-shortest",
            str(output_path),
        ]
    else:
        cmd = [
            ffmpeg,
            "-y",
            "-stream_loop",
            "-1",
            "-i",
            str(video_path),
            "-t",
            str(duration_sec),
            "-vf",
            vf,
            "-c:v",
            "libx264",
            "-pix_fmt",
            "yuv420p",
            "-r",
            "24",
            "-an",
            str(output_path),
        ]
    subprocess.run(cmd, check=True, capture_output=True, text=True)
    return output_path


async def build_factory_video(
    segments: list[ShortVideoSegment],
    *,
    task_dir: Path,
    width: int,
    height: int,
    segment_seconds: float = DEFAULT_SEGMENT_SECONDS,
    enable_tts: bool = False,
    visual_source: str = "slide",
    stock_provider: str = "pexels",
    aspect: str = "9:16",
) -> Path:
    from services.stock_material_service import search_and_fetch

    segment_paths: list[Path] = []
    use_stock = (visual_source or "slide").strip().lower() == "stock"

    for index, segment in enumerate(segments):
        segment_path = task_dir / f"segment_{index:02d}.mp4"
        duration_sec = (
            float(segment.duration_sec)
            if enable_tts and segment.duration_sec is not None
            else segment_seconds
        )
        audio_path = Path(segment.audio_path) if enable_tts and segment.audio_path else None

        stock_clip: Path | None = None
        if use_stock:
            query = (segment.visual_prompt or segment.narration or "").strip()
            stock_clip = await search_and_fetch(
                query,
                duration_sec=duration_sec,
                aspect=aspect,
                task_dir=task_dir,
                width=width,
                height=height,
                provider=stock_provider,
                segment_index=index,
            )
            if stock_clip is None:
                logger.warning(
                    "stock material unavailable, fallback to slide segment=%s query=%s",
                    index,
                    query,
                )

        if stock_clip is not None and stock_clip.is_file():
            stock_to_segment_mp4(
                stock_clip,
                segment_path,
                duration_sec=duration_sec,
                width=width,
                height=height,
                audio_path=audio_path,
            )
        else:
            image_path = task_dir / f"slide_{index:02d}.png"
            render_slide_image(segment.narration, width=width, height=height, output_path=image_path)
            image_to_segment_mp4(
                image_path,
                segment_path,
                duration_sec=duration_sec,
                width=width,
                height=height,
                audio_path=audio_path,
            )
        segment_paths.append(segment_path)

    final_path = task_dir / "final.mp4"
    concat_segments(segment_paths, final_path)
    return final_path


def relative_result_path(task_id: str) -> str:
    return f"data/short_video/{task_id}/final.mp4"


async def run_short_video_job(
    task_id: str,
    *,
    topic: str,
    segment_count: int,
    aspect: str,
    burn_captions: bool = False,
    bgm: str = "none",
    enable_tts: bool = True,
    voice_name: str = DEFAULT_VOICE_NAME,
    visual_source: str = "slide",
    stock_provider: str = "pexels",
) -> dict[str, Any]:
    from db.session import SessionLocal
    from models import Task

    db = SessionLocal()
    task = None
    try:
        task = db.get(Task, task_id)
        if task:
            task.status = "running"
            db.commit()

        width, height = aspect_to_size(aspect)
        task_dir = task_output_dir(task_id)
        segments = await generate_segments(topic, segment_count=segment_count)
        if enable_tts:
            segments = await synthesize_segments_audio(
                segments,
                task_dir=task_dir,
                voice_name=voice_name,
            )

        final_path = await build_factory_video(
            segments,
            task_dir=task_dir,
            width=width,
            height=height,
            enable_tts=enable_tts,
            visual_source=visual_source,
            stock_provider=stock_provider,
            aspect=aspect,
        )

        if burn_captions or (bgm or "").strip().lower() not in ("", "none", "skip"):
            from services.video_postprocess import apply_short_video_postprocess

            if enable_tts:
                cues = build_timeline_cues(segments)
            else:
                cues = build_uniform_cues(segments, segment_seconds=DEFAULT_SEGMENT_SECONDS)
            final_path = apply_short_video_postprocess(
                final_path,
                task_dir=task_dir,
                cues=cues,
                bgm=bgm,
                aspect=aspect,
                burn_captions=burn_captions,
            )

        rel = relative_result_path(task_id)
        if task:
            task.status = "completed"
            task.result = rel
            task.completed_at = datetime.now(timezone.utc)
            task.error = None
            db.commit()
        return {"task_id": task_id, "status": "completed", "result_path": rel}
    except Exception as exc:
        logger.exception("short video factory failed task_id=%s", task_id)
        if task:
            task.status = "failed"
            task.error = str(exc)[:2000]
            db.commit()
        raise
    finally:
        db.close()
