"""视频 faststart remux：将 moov 移到文件头，加速浏览器起播。"""

from __future__ import annotations

import asyncio
import logging
import re
import shutil
import subprocess
import tempfile
import uuid
from pathlib import Path
from urllib.parse import parse_qs, urlparse

import httpx

from services.media_access import (
    _resolve_comfy_output_path,
    append_media_ticket,
    grant_output_access,
    issue_media_ticket,
    normalize_media_reference_url,
    resolve_upload_file_path,
    sanitize_filename,
)
from services.video_enhance_probe import _ffmpeg_executable

logger = logging.getLogger(__name__)

UPLOADS_VIDEOS = Path(__file__).resolve().parent.parent / "uploads" / "videos"
_FASTSTART_SUFFIX = "_fs.mp4"
_faststart_jobs: set[str] = set()


def _sign_result_url_for_user(url: str | None, user_id: int) -> str | None:
    if not url or not user_id:
        return url
    grant_output_access(user_id, url)
    ticket = issue_media_ticket(user_id)["media_ticket"]
    if url.startswith("http://") or url.startswith("https://"):
        return append_media_ticket(url, ticket)
    if url.startswith("/"):
        return append_media_ticket(url, ticket)
    return append_media_ticket(f"/api/view?filename={url}&type=output", ticket)


def remux_mp4_faststart(src: Path, dst: Path, *, timeout_sec: int = 600) -> None:
    """ffmpeg copy remux，将 moov 移到文件头。"""
    dst.parent.mkdir(parents=True, exist_ok=True)
    ffmpeg = _ffmpeg_executable()
    cmd = [
        ffmpeg,
        "-nostdin",
        "-y",
        "-i",
        str(src),
        "-c",
        "copy",
        "-movflags",
        "+faststart",
        str(dst),
    ]
    proc = subprocess.run(
        cmd,
        capture_output=True,
        text=True,
        timeout=timeout_sec,
        check=False,
    )
    if proc.returncode != 0 or not dst.is_file():
        tail = (proc.stderr or proc.stdout or "")[-2000:]
        raise RuntimeError(f"ffmpeg faststart remux failed: {tail}")


def _parse_view_params(result_url: str) -> tuple[str, str, str | None]:
    parsed = urlparse(result_url)
    query = parse_qs(parsed.query)
    filename = (query.get("filename") or [""])[0].strip()
    subfolder = (query.get("subfolder") or [""])[0].strip()
    node = (query.get("node") or [None])[0]
    return filename, subfolder, node


def _uploads_video_path(result_url: str) -> Path | None:
    raw = normalize_media_reference_url((result_url or "").strip())
    if not raw or "/api/uploads/videos/" not in raw and not raw.startswith("uploads/videos/"):
        return None
    try:
        rel = raw.split("/api/uploads/", 1)[-1].split("?", 1)[0]
        if rel.startswith("uploads/"):
            rel = rel[len("uploads/") :]
        return resolve_upload_file_path(rel)
    except Exception:
        return None


def _download_comfy_video(
    filename: str,
    *,
    subfolder: str = "",
    node_port: str | None = None,
) -> Path | None:
    from core.comfyui_settings import resolve_comfyui_node_url
    from urllib.parse import quote

    safe_name = sanitize_filename(filename)
    if not safe_name:
        return None
    base = resolve_comfyui_node_url(node_port).rstrip("/")
    params = f"filename={quote(safe_name, safe='')}&type=output"
    if subfolder:
        params += f"&subfolder={quote(subfolder, safe='')}"
    url = f"{base}/view?{params}"
    tmp = Path(tempfile.mkdtemp(prefix="aistudio_fs_")) / safe_name
    try:
        with httpx.Client(timeout=httpx.Timeout(300.0, connect=30.0)) as client:
            res = client.get(url)
            res.raise_for_status()
            tmp.write_bytes(res.content)
        return tmp if tmp.is_file() else None
    except Exception as exc:
        logger.warning("download comfy video for faststart failed: %s", exc)
        return None


def _is_local_comfy_node(node_port: str | None) -> bool:
    """node= 指向本机 ComfyUI 时才可直接读本地 output，避免远程同名文件被本地旧片顶替。"""
    if not (node_port or "").strip():
        return True
    from core.comfyui_settings import resolve_comfyui_node_url

    host = (urlparse(resolve_comfyui_node_url(node_port)).hostname or "").lower()
    return host in ("127.0.0.1", "localhost", "::1")


def _resolve_source_video_path(result_url: str) -> tuple[Path | None, Path | None]:
    """
    解析源视频路径。
    返回 (source_path, temp_dir_or_none)；temp_dir 需在 remux 后清理。
    """
    raw = normalize_media_reference_url((result_url or "").strip())
    if not raw:
        return None, None

    upload_path = _uploads_video_path(raw)
    if upload_path and upload_path.is_file():
        return upload_path, None

    if raw.startswith("http://") or raw.startswith("https://"):
        return None, None

    if "/api/view" in raw or "filename=" in raw:
        filename, subfolder, node_port = _parse_view_params(raw)
        if not filename:
            return None, None
        # 远程节点产出必须按 node= 拉取；本地同名旧文件（如 AIStudio_video_00003.mp4）不可抢先命中
        use_local = _is_local_comfy_node(node_port)
        if use_local:
            local = _resolve_comfy_output_path(filename, subfolder)
            if local and local.is_file():
                return local, None
        downloaded = _download_comfy_video(
            filename,
            subfolder=subfolder,
            node_port=node_port,
        )
        if downloaded and downloaded.is_file():
            return downloaded, downloaded.parent
        if not use_local:
            local = _resolve_comfy_output_path(filename, subfolder)
            if local and local.is_file():
                logger.warning(
                    "faststart fallback to local output after remote download failed: %s node=%s",
                    filename,
                    node_port,
                )
                return local, None
    return None, None


def _output_name_for(task_id: str | None, src: Path) -> str:
    stem = re.sub(r"[^A-Za-z0-9._-]+", "_", src.stem)[:80] or "video"
    prefix = (task_id or uuid.uuid4().hex)[:36]
    return f"{prefix}_{stem}{_FASTSTART_SUFFIX}"


def ensure_video_result_faststart(
    result_url: str | None,
    *,
    task_id: str | None = None,
) -> str | None:
    """
    将视频结果 remux 为 faststart MP4 并落到 uploads/videos。
    失败时原样返回 result_url，不阻断任务完成。
    """
    if not result_url or not str(result_url).strip():
        return result_url

    raw = normalize_media_reference_url(str(result_url).strip())
    if raw.startswith("http://") or raw.startswith("https://"):
        return result_url
    if raw.endswith(_FASTSTART_SUFFIX):
        return result_url

    src_path, temp_dir = _resolve_source_video_path(result_url)
    if not src_path or not src_path.is_file():
        return result_url

    UPLOADS_VIDEOS.mkdir(parents=True, exist_ok=True)
    out_name = _output_name_for(task_id, src_path)
    out_path = UPLOADS_VIDEOS / out_name
    if out_path.is_file():
        return f"/api/uploads/videos/{out_name}"

    try:
        remux_mp4_faststart(src_path, out_path)
        logger.info(
            "faststart remux ok task_id=%s src=%s dst=%s",
            task_id,
            src_path.name,
            out_name,
        )
        return f"/api/uploads/videos/{out_name}"
    except Exception as exc:
        logger.warning(
            "faststart remux failed task_id=%s src=%s: %s",
            task_id,
            src_path,
            exc,
        )
        return result_url
    finally:
        if temp_dir and temp_dir.exists():
            shutil.rmtree(temp_dir, ignore_errors=True)


async def _run_video_faststart_job(
    task_id: str,
    result_url: str,
    user_id: int,
) -> None:
    from db.session import SessionLocal
    from models import Task

    try:
        new_url = await asyncio.to_thread(
            ensure_video_result_faststart,
            result_url,
            task_id=task_id,
        )
        if not new_url or new_url == result_url or not new_url.endswith(_FASTSTART_SUFFIX):
            return
        signed = _sign_result_url_for_user(new_url, user_id)
        if not signed:
            return
        db = SessionLocal()
        try:
            task = db.get(Task, task_id)
            if not task or task.status != "completed":
                return
            current = normalize_media_reference_url(str(task.result or ""))
            if current.endswith(_FASTSTART_SUFFIX):
                return
            task.result = signed
            db.commit()
            logger.info("faststart upgraded task result task_id=%s", task_id)
        finally:
            db.close()
    except Exception:
        logger.exception("faststart background job failed task_id=%s", task_id)
    finally:
        _faststart_jobs.discard(task_id)


def schedule_video_faststart(
    task_id: str | None,
    result_url: str | None,
    user_id: int | None,
) -> None:
    """后台 remux，不阻塞任务完成响应；完成后更新 task.result 为 uploads faststart URL。"""
    if not task_id or not result_url or not user_id:
        return
    raw = normalize_media_reference_url(str(result_url).strip())
    if not raw or raw.startswith("http://") or raw.startswith("https://"):
        return
    if raw.endswith(_FASTSTART_SUFFIX):
        return
    if task_id in _faststart_jobs:
        return
    _faststart_jobs.add(task_id)
    asyncio.create_task(_run_video_faststart_job(task_id, result_url, user_id))

