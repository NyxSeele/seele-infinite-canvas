"""镜头级视频风格参考：抽帧、VL 分析、LLM 汇总与 prompt 注入。"""

from __future__ import annotations

import json
import logging
import re
import shutil
import subprocess
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from uuid import uuid4

from fastapi import HTTPException
from sqlalchemy.orm import Session

from models.canvas_project import CanvasProject
from services.canvas_style_ref import (
    clear_video_node_style_reference,
    get_video_node_style_reference,
    load_canvas_data,
    patch_video_node_style_reference,
    resolve_video_node_for_shot,
)
from services.media_access import append_media_ticket, issue_media_ticket
from services.qwen import _call_llm
from services.qwen_vision import describe_frame_vl
from services.upload_validation import (
    MAX_STYLE_VIDEO_SECONDS,
    validate_style_video_upload,
    video_suffix_for_mime,
)

logger = logging.getLogger(__name__)

STYLE_VIDEO_DIR = Path("uploads/videos")
STYLE_VIDEO_DIR.mkdir(parents=True, exist_ok=True)

_AGGREGATE_SYSTEM = """You are a cinematography analyst. Given per-frame descriptions from a reference video,
output a single JSON object (no markdown fences) with these keys:
{
  "color_tone": "English phrase for color grading",
  "lighting": "English phrase for lighting",
  "shot_language": "English phrase for shot types and camera work",
  "atmosphere": "English mood/atmosphere phrase",
  "style_keywords": ["english", "tag", "list", "5-8 items"],
  "display_summary": "One concise Chinese sentence summarizing the visual style for UI display"
}
All style fields must be in English except display_summary (Chinese). Be specific and cinematic."""


def _ffmpeg_executable() -> str:
    try:
        import imageio_ffmpeg

        return imageio_ffmpeg.get_ffmpeg_exe()
    except Exception as exc:
        raise HTTPException(status_code=503, detail="ffmpeg 不可用，无法分析视频") from exc


def probe_video_duration(video_path: Path) -> float:
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
    match = re.search(r"Duration:\s*(\d+):(\d+):(\d+(?:\.\d+)?)", stderr)
    if not match:
        raise HTTPException(status_code=400, detail="无法解析视频时长")
    hours, minutes, seconds = match.groups()
    return int(hours) * 3600 + int(minutes) * 60 + float(seconds)


def extract_video_frames(video_path: Path, out_dir: Path, count: int = 8) -> list[Path]:
    duration = probe_video_duration(video_path)
    if duration > MAX_STYLE_VIDEO_SECONDS + 0.5:
        raise HTTPException(
            status_code=400,
            detail=f"视频时长不能超过 {MAX_STYLE_VIDEO_SECONDS} 秒",
        )
    if duration <= 0:
        raise HTTPException(status_code=400, detail="视频时长无效")

    ffmpeg = _ffmpeg_executable()
    frames: list[Path] = []
    n = max(6, min(count, 8))
    for i in range(n):
        ts = max(0.0, (duration * (i + 0.5) / n) - 0.05)
        out = out_dir / f"frame_{i:02d}.jpg"
        try:
            subprocess.run(
                [
                    ffmpeg,
                    "-y",
                    "-ss",
                    f"{ts:.3f}",
                    "-i",
                    str(video_path),
                    "-frames:v",
                    "1",
                    "-q:v",
                    "2",
                    str(out),
                ],
                check=True,
                capture_output=True,
                timeout=60,
            )
        except (subprocess.CalledProcessError, subprocess.TimeoutExpired) as exc:
            logger.warning("frame extract failed at %s: %s", ts, exc)
            continue
        if out.is_file() and out.stat().st_size > 0:
            frames.append(out)
    if not frames:
        raise HTTPException(status_code=400, detail="无法从视频中抽取有效帧")
    return frames


def parse_style_reference(raw: str | None) -> dict | None:
    if not raw or not str(raw).strip():
        return None
    try:
        data = json.loads(raw)
    except json.JSONDecodeError:
        return None
    return data if isinstance(data, dict) else None


def dump_style_reference(data: dict) -> str:
    return json.dumps(data, ensure_ascii=False)


def format_style_for_prompt(ref: dict | None) -> str:
    if not ref or not isinstance(ref, dict):
        return ""
    color = (ref.get("color_tone") or "").strip()
    lighting = (ref.get("lighting") or "").strip()
    shot_lang = (ref.get("shot_language") or "").strip()
    parts = [p for p in (color, lighting, shot_lang) if p]
    block = ""
    if parts:
        block = f"[风格参考：{'，'.join(parts)}]"
    keywords = ref.get("style_keywords") or []
    kw = [str(k).strip() for k in keywords if str(k).strip()]
    if kw:
        kw_text = ", ".join(kw)
        block = f"{block} {kw_text}".strip() if block else kw_text
    return block


def _clean_json_response(raw: str) -> dict:
    text = (raw or "").strip()
    if text.startswith("```"):
        text = re.sub(r"^```(?:json)?\s*", "", text)
        text = re.sub(r"\s*```$", "", text)
    try:
        data = json.loads(text)
    except json.JSONDecodeError as exc:
        raise HTTPException(status_code=503, detail="风格分析结果解析失败") from exc
    if not isinstance(data, dict):
        raise HTTPException(status_code=503, detail="风格分析结果格式无效")
    return data


async def aggregate_style_json(frame_descriptions: list[str]) -> dict:
    numbered = "\n\n".join(
        f"Frame {i + 1}:\n{desc}" for i, desc in enumerate(frame_descriptions)
    )
    user_prompt = f"Reference video frame analyses:\n\n{numbered}"
    raw, _ = await _call_llm(_AGGREGATE_SYSTEM, user_prompt, max_tokens=2000)
    data = _clean_json_response(raw)
    keywords = data.get("style_keywords") or []
    if not isinstance(keywords, list):
        keywords = []
    return {
        "color_tone": str(data.get("color_tone") or "").strip(),
        "lighting": str(data.get("lighting") or "").strip(),
        "shot_language": str(data.get("shot_language") or "").strip(),
        "atmosphere": str(data.get("atmosphere") or "").strip(),
        "style_keywords": [str(k).strip() for k in keywords if str(k).strip()],
        "display_summary": str(data.get("display_summary") or "").strip(),
        "source": "user_upload",
        "extracted_at": datetime.now(timezone.utc).isoformat(),
    }


def _delete_source_video(url: str) -> None:
    if not url or "/api/uploads/videos/" not in url:
        return
    name = url.split("/api/uploads/videos/")[-1].split("?")[0]
    if not name or "/" in name or ".." in name:
        return
    path = STYLE_VIDEO_DIR / name
    if path.is_file():
        try:
            path.unlink()
        except OSError:
            logger.warning("failed to delete style video %s", path)


async def analyze_video_bytes(
    content: bytes,
    *,
    declared_mime: str | None,
    user_id: int,
) -> dict:
    mime = validate_style_video_upload(content, declared_mime)
    suffix = video_suffix_for_mime(mime)
    filename = f"{uuid4()}{suffix}"
    save_path = STYLE_VIDEO_DIR / filename

    with tempfile.TemporaryDirectory() as tmp:
        tmp_video = Path(tmp) / f"input{suffix}"
        tmp_video.write_bytes(content)
        duration = probe_video_duration(tmp_video)
        if duration > MAX_STYLE_VIDEO_SECONDS + 0.5:
            raise HTTPException(
                status_code=400,
                detail=f"视频时长不能超过 {MAX_STYLE_VIDEO_SECONDS} 秒",
            )
        frames = extract_video_frames(tmp_video, Path(tmp), count=8)
        descriptions: list[str] = []
        for frame in frames:
            try:
                desc = await describe_frame_vl(frame)
                descriptions.append(desc)
            except Exception as exc:
                logger.warning("VL describe failed: %s", exc)
        if not descriptions:
            raise HTTPException(status_code=503, detail="视频风格分析失败，请稍后重试")

        style_data = await aggregate_style_json(descriptions)
        if not style_data.get("style_keywords"):
            raise HTTPException(status_code=503, detail="未能提取有效风格关键词")

    save_path.write_bytes(content)
    ticket = issue_media_ticket(user_id)["media_ticket"]
    rel = f"videos/{filename}"
    style_data["source_video_url"] = append_media_ticket(f"/api/uploads/{rel}", ticket)
    return style_data


async def analyze_and_patch_node(
    db: Session,
    project: CanvasProject,
    node_id: str,
    content: bytes,
    *,
    declared_mime: str | None,
    user_id: int,
    script_table_node_id: str | None = None,
    row_id: str | None = None,
) -> dict:
    canvas_data = load_canvas_data(project)
    old = get_video_node_style_reference(canvas_data, node_id)
    if old and old.get("source_video_url"):
        _delete_source_video(old["source_video_url"])

    style_data = await analyze_video_bytes(
        content, declared_mime=declared_mime, user_id=user_id
    )
    patch_video_node_style_reference(
        project,
        node_id,
        style_data,
        script_table_node_id=script_table_node_id,
        row_id=row_id,
    )
    db.commit()
    db.refresh(project)
    return style_data


def update_node_style_reference(
    project: CanvasProject,
    node_id: str,
    patch: dict,
    *,
    script_table_node_id: str | None = None,
    row_id: str | None = None,
) -> dict:
    canvas_data = load_canvas_data(project)
    current = get_video_node_style_reference(canvas_data, node_id) or {}
    for key in (
        "color_tone",
        "lighting",
        "shot_language",
        "atmosphere",
        "style_keywords",
        "display_summary",
    ):
        if key in patch and patch[key] is not None:
            current[key] = patch[key]
    if not current.get("extracted_at"):
        current["extracted_at"] = datetime.now(timezone.utc).isoformat()
    if not current.get("source"):
        current["source"] = "user_upload"
    return patch_video_node_style_reference(
        project,
        node_id,
        current,
        script_table_node_id=script_table_node_id,
        row_id=row_id,
    )


def clear_node_style_reference(
    project: CanvasProject,
    node_id: str,
    *,
    script_table_node_id: str | None = None,
    row_id: str | None = None,
) -> None:
    canvas_data = load_canvas_data(project)
    old = get_video_node_style_reference(canvas_data, node_id)
    if old and old.get("source_video_url"):
        _delete_source_video(old["source_video_url"])
    clear_video_node_style_reference(
        project,
        node_id,
        script_table_node_id=script_table_node_id,
        row_id=row_id,
    )


def get_node_style_reference(
    project: CanvasProject,
    node_id: str,
) -> dict | None:
    return get_video_node_style_reference(load_canvas_data(project), node_id)


def resolve_shot_video_node_id(
    project: CanvasProject,
    script_table_node_id: str,
    row_id: str,
) -> str:
    return resolve_video_node_for_shot(
        load_canvas_data(project), script_table_node_id, row_id
    )
