"""G45: 视频逐帧 ReActor 换脸（独立工作流，不跑 PuLID）。"""

from __future__ import annotations

import asyncio
import logging
import re
import shutil
import subprocess
import time
from pathlib import Path

import httpx

from db.session import SessionLocal
from models import Task, User
from services.media_access import (
    grant_output_access,
    resolve_image_reference_path,
    resolve_video_source_for_enhance,
)

logger = logging.getLogger(__name__)

BACKEND_DIR = Path(__file__).resolve().parent.parent
TMP_ROOT = BACKEND_DIR / "tmp"
UPLOADS_VIDEOS = BACKEND_DIR / "uploads" / "videos"
COMFY_OUTPUT = Path("/root/autodl-tmp/ComfyUI/output")


def _ffmpeg_bin() -> str:
    """优先系统 ffmpeg；避免 video_enhance_probe 在无 imageio_ffmpeg 时抛 503。"""
    for candidate in ("ffmpeg", "/usr/bin/ffmpeg"):
        path = shutil.which(candidate) if candidate == "ffmpeg" else candidate
        if path and Path(path).is_file():
            return path
    try:
        import imageio_ffmpeg

        return imageio_ffmpeg.get_ffmpeg_exe()
    except Exception as exc:
        raise RuntimeError("ffmpeg 不可用") from exc


def tmp_reactor_dir(task_id: str) -> Path:
    safe = re.sub(r"[^a-zA-Z0-9_-]", "", (task_id or "x")[:64]) or "x"
    return TMP_ROOT / f"tmp_reactor_{safe}"


def cleanup_tmp_reactor(task_id: str) -> None:
    d = tmp_reactor_dir(task_id)
    if d.exists():
        shutil.rmtree(d, ignore_errors=True)
        logger.info("G45 cleaned %s", d)


def probe_video_fps(video_path: Path) -> float:
    ffmpeg = _ffmpeg_bin()
    try:
        proc = subprocess.run(
            [ffmpeg, "-i", str(video_path)],
            capture_output=True,
            text=True,
            timeout=30,
        )
        text = (proc.stderr or "") + (proc.stdout or "")
        m = re.search(r"(\d+(?:\.\d+)?)\s*fps", text)
        if m:
            fps = float(m.group(1))
            if 1.0 <= fps <= 120.0:
                return fps
        m2 = re.search(r"(\d+)/(\d+)\s*fps", text)
        if m2:
            num, den = float(m2.group(1)), float(m2.group(2))
            if den > 0:
                fps = num / den
                if 1.0 <= fps <= 120.0:
                    return fps
    except Exception as exc:
        logger.warning("G45 fps probe failed: %s", exc)
    return 24.0


def extract_all_frames(video_path: Path, out_dir: Path, *, max_frames: int | None = None) -> list[Path]:
    """ffmpeg 拆全部帧到 out_dir/frame_%06d.png。"""
    out_dir.mkdir(parents=True, exist_ok=True)
    pattern = out_dir / "frame_%06d.png"
    ffmpeg = _ffmpeg_bin()
    cmd = [ffmpeg, "-y", "-i", str(video_path), "-vsync", "0", str(pattern)]
    subprocess.run(cmd, check=True, capture_output=True, timeout=600)
    frames = sorted(out_dir.glob("frame_*.png"))
    if max_frames is not None and max_frames > 0 and len(frames) > max_frames:
        # 均匀保留 max_frames，删其余以省盘
        keep = set()
        n = len(frames)
        for i in range(max_frames):
            idx = int(i * (n - 1) / max(max_frames - 1, 1))
            keep.add(frames[idx])
        for f in frames:
            if f not in keep:
                f.unlink(missing_ok=True)
        frames = sorted(keep)
    if not frames:
        raise RuntimeError(f"拆帧失败：无输出 {out_dir}")
    return frames


def remux_frames_with_audio(
    frames_dir: Path,
    source_video: Path,
    output_path: Path,
    *,
    fps: float,
) -> Path:
    """合帧并尽量混入原音轨 → *_swapped.mp4。"""
    output_path = Path(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    ffmpeg = _ffmpeg_bin()
    pattern = str(frames_dir / "swapped_%06d.png")
    # 先合成无音视频，再尝试挂原音轨
    silent = output_path.with_suffix(".silent.mp4")
    cmd_v = [
        ffmpeg,
        "-y",
        "-framerate",
        f"{fps:.6f}",
        "-i",
        pattern,
        "-c:v",
        "libx264",
        "-pix_fmt",
        "yuv420p",
        "-movflags",
        "+faststart",
        str(silent),
    ]
    subprocess.run(cmd_v, check=True, capture_output=True, timeout=600)

    cmd_a = [
        ffmpeg,
        "-y",
        "-i",
        str(silent),
        "-i",
        str(source_video),
        "-map",
        "0:v:0",
        "-map",
        "1:a:0?",
        "-c:v",
        "copy",
        "-c:a",
        "aac",
        "-shortest",
        str(output_path),
    ]
    try:
        subprocess.run(cmd_a, check=True, capture_output=True, timeout=300)
    except subprocess.CalledProcessError:
        shutil.copy2(silent, output_path)
    finally:
        silent.unlink(missing_ok=True)
    if not output_path.is_file():
        raise RuntimeError(f"合帧失败: {output_path}")
    return output_path


async def _upload_local_image(path: Path, *, node_url: str | None = None) -> str:
    from providers.comfyui import _upload_image_bytes

    data = path.read_bytes()
    suffix = path.suffix.lower() or ".png"
    mime = "image/png" if suffix == ".png" else "image/jpeg"
    return await _upload_image_bytes(data, path.name, mime, base_url=node_url)


async def _wait_image_filename(
    prompt_id: str, *, timeout_sec: float = 180.0, node_url: str | None = None
) -> str:
    from providers.comfyui import get_image_result

    deadline = time.monotonic() + timeout_sec
    while time.monotonic() < deadline:
        result = await get_image_result(prompt_id, node_url=node_url)
        if isinstance(result, dict) and result.get("error"):
            raise RuntimeError(str(result["error"]))
        if isinstance(result, str) and result:
            return result
        await asyncio.sleep(0.4)
    raise TimeoutError(f"ReActor 帧超时 prompt_id={prompt_id}")


async def _download_comfy_image(
    filename: str, dest: Path, *, node_url: str | None = None
) -> Path:
    """优先拷贝 ComfyUI/output；否则 /view 下载。"""
    dest.parent.mkdir(parents=True, exist_ok=True)
    local = COMFY_OUTPUT / filename
    if local.is_file():
        shutil.copy2(local, dest)
        return dest
    matches = list(COMFY_OUTPUT.rglob(filename))
    if matches:
        shutil.copy2(matches[0], dest)
        return dest
    from comfyui.client import _resolve_comfyui_base
    from urllib.parse import quote

    base = _resolve_comfyui_base(node_url)
    url = f"{base}/view?filename={quote(filename, safe='')}&type=output"
    async with httpx.AsyncClient(timeout=60.0) as client:
        res = await client.get(url)
        res.raise_for_status()
        dest.write_bytes(res.content)
    return dest


async def swap_single_frame(
    frame_path: Path,
    face_comfy_name: str,
    out_path: Path,
    *,
    prefix: str = "AIStudio_reactor_frame",
    node_url: str | None = None,
) -> Path:
    from comfyui.client import _acquire_gpu_node_url, _post_workflow
    from providers.comfyui import build_reactor_frame_workflow

    base = node_url or _acquire_gpu_node_url(required_vram=12)
    frame_name = await _upload_local_image(frame_path, node_url=base)
    workflow = build_reactor_frame_workflow(
        frame_filename=frame_name,
        face_filename=face_comfy_name,
        filename_prefix=prefix,
    )
    prompt_id, _, posted_node = await _post_workflow(workflow, None, node_url=base)
    out_name = await _wait_image_filename(prompt_id, node_url=posted_node)
    return await _download_comfy_image(out_name, out_path, node_url=posted_node)


async def swap_faces_in_video(
    video_path: Path,
    face_image_path: Path,
    output_path: Path,
    *,
    task_id: str,
    max_frames: int | None = None,
) -> Path:
    """
    拆帧 → 逐帧 ReActor → 合帧+原音轨。
    临时目录 tmp_reactor_{task_id} 在 finally 中删除。
    """
    video_path = Path(video_path)
    face_image_path = Path(face_image_path)
    output_path = Path(output_path)
    work = tmp_reactor_dir(task_id)
    frames_in = work / "in"
    frames_out = work / "out"
    try:
        if work.exists():
            shutil.rmtree(work, ignore_errors=True)
        frames_in.mkdir(parents=True, exist_ok=True)
        frames_out.mkdir(parents=True, exist_ok=True)

        fps = probe_video_fps(video_path)
        frames = extract_all_frames(video_path, frames_in, max_frames=max_frames)
        logger.info("G45 extracted %s frames fps=%.3f task_id=%s", len(frames), fps, task_id)

        from comfyui.client import _acquire_gpu_node_url

        reactor_node = _acquire_gpu_node_url(required_vram=12)
        face_comfy = await _upload_local_image(face_image_path, node_url=reactor_node)
        for i, frame in enumerate(frames, start=1):
            out_frame = frames_out / f"swapped_{i:06d}.png"
            await swap_single_frame(
                frame,
                face_comfy,
                out_frame,
                prefix=f"AIStudio_g45_{task_id[:8]}",
                node_url=reactor_node,
            )
            if i % 10 == 0 or i == len(frames):
                logger.info("G45 frame %s/%s task_id=%s", i, len(frames), task_id)

        return remux_frames_with_audio(frames_out, video_path, output_path, fps=fps)
    finally:
        cleanup_tmp_reactor(task_id)


async def maybe_apply_reactor_video(task_id: str) -> None:
    """后台：失败只记日志，保留原成片；成功后链式 G39 sound_note。"""
    try:
        await _apply_reactor_video(task_id)
    except Exception as exc:
        logger.exception("G45 reactor video failed task_id=%s: %s", task_id, exc)
    finally:
        # 无论换脸成败，若有 sound_note 仍尝试混音（基于当前 task.result）
        try:
            from services.audiogen_postprocess import maybe_apply_sound_note_mix

            await maybe_apply_sound_note_mix(task_id)
        except Exception as exc:
            logger.exception("G45→G39 chain failed task_id=%s: %s", task_id, exc)


async def _apply_reactor_video(task_id: str) -> None:
    db = SessionLocal()
    try:
        task = db.get(Task, task_id)
        if not task or task.status != "completed" or not task.result:
            return
        if "_swapped" in str(task.result or ""):
            logger.info("G45 skip already swapped task_id=%s", task_id)
            return
        if not bool(getattr(task, "use_reactor", False)):
            return
        face_url = (getattr(task, "reactor_face_image", None) or "").strip()
        if not face_url:
            logger.warning("G45 use_reactor but no reactor_face_image task_id=%s", task_id)
            return

        user = db.get(User, task.user_id) if task.user_id else None
        if not user:
            logger.warning("G45 no user task_id=%s", task_id)
            return

        video_path = resolve_video_source_for_enhance(db, user, task.result)
        if not video_path or not Path(video_path).is_file():
            logger.warning("G45 video missing task_id=%s", task_id)
            return
        face_path = resolve_image_reference_path(db, user, face_url)
        if not face_path.is_file():
            logger.warning("G45 face missing task_id=%s path=%s", task_id, face_path)
            return

        UPLOADS_VIDEOS.mkdir(parents=True, exist_ok=True)
        out_path = UPLOADS_VIDEOS / f"{Path(video_path).stem}_swapped.mp4"
        swapped = await swap_faces_in_video(
            Path(video_path),
            Path(face_path),
            out_path,
            task_id=task_id,
        )
        new_url = f"/api/uploads/videos/{swapped.name}"
        if task.user_id:
            grant_output_access(task.user_id, new_url)
        # 重新读 task，避免长任务后 session 过期
        task = db.get(Task, task_id)
        if task:
            task.result = new_url
            db.commit()
        logger.info("G45 reactor ok task_id=%s result=%s", task_id, new_url)
    finally:
        db.close()
        cleanup_tmp_reactor(task_id)
