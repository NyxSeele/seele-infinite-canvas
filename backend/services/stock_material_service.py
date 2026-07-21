"""Stock material search and fetch for short-video factory."""

from __future__ import annotations

import hashlib
import logging
import os
import random
import re
import shutil
import subprocess
import threading
from pathlib import Path
from typing import Any
from urllib.parse import urlencode

import httpx

from services.video_enhance_probe import _ffmpeg_executable

logger = logging.getLogger(__name__)

PROJECT_ROOT = Path(__file__).resolve().parents[2]
CACHE_ROOT = PROJECT_ROOT / "data" / "short_video_cache"
LOCAL_STOCK_ROOT = PROJECT_ROOT / "data" / "short_video_stock"
PEXELS_SEARCH_URL = "https://api.pexels.com/videos/search"

_api_key_counter = 0
_api_key_lock = threading.Lock()
_MAX_DOWNLOAD_BYTES = 80 * 1024 * 1024


def is_mock_stock() -> bool:
    return os.environ.get("SHORT_VIDEO_MOCK_STOCK", "").strip().lower() in ("1", "true", "yes")


def aspect_to_orientation(aspect: str) -> str:
    normalized = (aspect or "9:16").strip().lower()
    if normalized in ("16:9", "landscape"):
        return "landscape"
    if normalized in ("1:1", "square"):
        return "square"
    return "portrait"


def _rotate_pexels_api_key() -> str | None:
    raw = (os.environ.get("PEXELS_API_KEY") or os.environ.get("PEXELS_API_KEYS") or "").strip()
    if not raw:
        return None
    keys = [part.strip() for part in re.split(r"[,，]", raw) if part.strip()]
    if not keys:
        return None
    if len(keys) == 1:
        return keys[0]
    global _api_key_counter
    with _api_key_lock:
        _api_key_counter += 1
        return keys[_api_key_counter % len(keys)]


def _cache_path_for_url(url: str) -> Path:
    digest = hashlib.sha256(url.encode("utf-8")).hexdigest()[:32]
    return CACHE_ROOT / f"{digest}.mp4"


async def _download_to_path(url: str, dest: Path, *, headers: dict[str, str] | None = None) -> Path:
    dest.parent.mkdir(parents=True, exist_ok=True)
    tmp = dest.with_suffix(dest.suffix + ".part")
    total = 0
    timeout = httpx.Timeout(60.0, connect=30.0)
    async with httpx.AsyncClient(timeout=timeout, follow_redirects=True) as client:
        async with client.stream("GET", url, headers=headers or {}) as resp:
            resp.raise_for_status()
            with tmp.open("wb") as handle:
                async for chunk in resp.aiter_bytes(1024 * 1024):
                    total += len(chunk)
                    if total > _MAX_DOWNLOAD_BYTES:
                        raise ValueError("stock download exceeds size limit")
                    handle.write(chunk)
    tmp.replace(dest)
    return dest


def _generate_mock_stock_clip(
    output_path: Path,
    *,
    width: int,
    height: int,
    duration_sec: float,
    color: str = "0x1a2030",
) -> Path:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    ffmpeg = _ffmpeg_executable()
    cmd = [
        ffmpeg,
        "-y",
        "-f",
        "lavfi",
        "-i",
        f"color=c={color}:s={width}x{height}:d={max(duration_sec, 0.5)}",
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


def _pick_local_stock(query: str) -> Path | None:
    if not LOCAL_STOCK_ROOT.is_dir():
        return None
    candidates: list[Path] = []
    tokens = [t for t in re.split(r"\s+", (query or "").strip().lower()) if t]
    for path in LOCAL_STOCK_ROOT.rglob("*"):
        if not path.is_file():
            continue
        if path.suffix.lower() not in {".mp4", ".mov", ".webm", ".mkv", ".jpg", ".jpeg", ".png"}:
            continue
        name = path.stem.lower()
        if not tokens or any(token in name for token in tokens):
            candidates.append(path)
    if not candidates:
        candidates = [
            p
            for p in LOCAL_STOCK_ROOT.rglob("*")
            if p.is_file() and p.suffix.lower() in {".mp4", ".mov", ".webm", ".mkv"}
        ]
    if not candidates:
        return None
    return random.choice(candidates)


def _select_pexels_file(
    videos: list[dict[str, Any]],
    *,
    width: int,
    height: int,
    minimum_duration: float,
) -> str | None:
    for video in videos:
        if float(video.get("duration") or 0) < minimum_duration:
            continue
        files = video.get("video_files") or []
        exact = [
            f
            for f in files
            if int(f.get("width") or 0) == width and int(f.get("height") or 0) == height
        ]
        pool = exact or sorted(files, key=lambda f: int(f.get("width") or 0), reverse=True)
        for item in pool:
            link = str(item.get("link") or "").strip()
            if link:
                return link
    return None


async def _search_pexels(
    query: str,
    *,
    width: int,
    height: int,
    aspect: str,
    minimum_duration: float,
) -> str | None:
    api_key = _rotate_pexels_api_key()
    if not api_key:
        return None
    params = {
        "query": query,
        "per_page": 20,
        "orientation": aspect_to_orientation(aspect),
    }
    headers = {"Authorization": api_key}
    timeout = httpx.Timeout(30.0, connect=15.0)
    async with httpx.AsyncClient(timeout=timeout, follow_redirects=True) as client:
        resp = await client.get(f"{PEXELS_SEARCH_URL}?{urlencode(params)}", headers=headers)
        resp.raise_for_status()
        payload = resp.json()
    videos = payload.get("videos") or []
    return _select_pexels_file(videos, width=width, height=height, minimum_duration=minimum_duration)


async def search_and_fetch(
    query: str,
    *,
    duration_sec: float,
    aspect: str,
    task_dir: Path,
    width: int,
    height: int,
    provider: str = "pexels",
    segment_index: int = 0,
) -> Path | None:
    """
    Search and fetch a stock clip for one segment.

    Returns local mp4 path on success, or None to signal slide fallback.
    """
    cleaned = (query or "").strip()
    if not cleaned:
        return None

    task_dir.mkdir(parents=True, exist_ok=True)
    segment_dest = task_dir / f"stock_{segment_index:02d}.mp4"

    if is_mock_stock():
        colors = ("0x1a2030", "0x203048", "0x283858", "0x304060")
        _generate_mock_stock_clip(
            segment_dest,
            width=width,
            height=height,
            duration_sec=duration_sec,
            color=colors[segment_index % len(colors)],
        )
        return segment_dest

    provider_name = (provider or "pexels").strip().lower()
    source_path: Path | None = None

    if provider_name == "local":
        source_path = _pick_local_stock(cleaned)
    else:
        try:
            download_url = await _search_pexels(
                cleaned,
                width=width,
                height=height,
                aspect=aspect,
                minimum_duration=max(1.0, duration_sec * 0.5),
            )
            if download_url:
                cache_path = _cache_path_for_url(download_url)
                if cache_path.is_file():
                    source_path = cache_path
                else:
                    CACHE_ROOT.mkdir(parents=True, exist_ok=True)
                    await _download_to_path(download_url, cache_path)
                    source_path = cache_path
        except Exception as exc:
            logger.warning("pexels search/download failed query=%s error=%s", cleaned, exc)

        if source_path is None:
            source_path = _pick_local_stock(cleaned)

    if source_path is None or not source_path.is_file():
        return None

    if source_path.suffix.lower() in {".jpg", ".jpeg", ".png"}:
        image_path = task_dir / f"stock_img_{segment_index:02d}{source_path.suffix}"
        shutil.copy2(source_path, image_path)
        ffmpeg = _ffmpeg_executable()
        cmd = [
            ffmpeg,
            "-y",
            "-loop",
            "1",
            "-i",
            str(image_path),
            "-t",
            str(max(duration_sec, 0.5)),
            "-vf",
            f"scale={width}:{height}",
            "-c:v",
            "libx264",
            "-pix_fmt",
            "yuv420p",
            "-r",
            "24",
            str(segment_dest),
        ]
        subprocess.run(cmd, check=True, capture_output=True, text=True)
        return segment_dest

    shutil.copy2(source_path, segment_dest)
    return segment_dest
