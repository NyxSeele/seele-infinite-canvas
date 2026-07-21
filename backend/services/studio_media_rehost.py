"""Rehost private studio media (/api/view, /api/uploads) to R2."""

from __future__ import annotations

import tempfile
from pathlib import Path
from urllib.parse import parse_qs, urlparse

import httpx
from fastapi import HTTPException
from sqlalchemy.orm import Session

from core.comfyui_settings import resolve_comfyui_node_url
from core.config import settings
from models import User
from services.media_access import (
    sanitize_filename,
    sanitize_upload_rel_path,
    user_can_access_comfy_output,
    user_can_access_upload,
)
from services.media_access import _resolve_comfy_output_path
from services.local_team_storage import save_local_file_from_path
from services.r2 import (
    R2NotConfiguredError,
    is_r2_configured,
    is_r2_public_asset_url,
    key_from_r2_public_url,
    upload_fileobj,
)
from services.storage_routing import resolve_backend

MAX_UPLOAD_BYTES = 2 * 1024 * 1024 * 1024
_UPLOAD_ROOT = Path("uploads")


def parse_studio_media_url(source_url: str) -> dict | None:
    """Detect /api/view or /api/uploads media; return {kind, ...} or None."""
    raw = (source_url or "").strip()
    if not raw:
        return None
    parsed = urlparse(raw)
    path = parsed.path or ""
    if not raw.startswith("/"):
        if not (path.startswith("/api/view") or path.startswith("/api/uploads/")):
            return None
    qs = parse_qs(parsed.query or "")
    if path == "/api/view" or path.endswith("/api/view"):
        filename = (qs.get("filename") or [None])[0]
        if not filename:
            return None
        return {
            "kind": "view",
            "filename": filename,
            "type": (qs.get("type") or ["output"])[0] or "output",
            "subfolder": (qs.get("subfolder") or [""])[0] or "",
        }
    if "/api/uploads/" in path:
        idx = path.find("/api/uploads/")
        rel = path[idx + len("/api/uploads/") :].lstrip("/")
        if not rel:
            return None
        return {"kind": "upload", "rel_path": rel}
    return None


def _video_content_type(filename: str) -> str:
    name = (filename or "").lower()
    if name.endswith(".webm"):
        return "video/webm"
    if name.endswith(".mov"):
        return "video/quicktime"
    if name.endswith(".mkv"):
        return "video/x-matroska"
    return "video/mp4"


def upload_path_to_local(
    file_path: Path,
    filename: str,
    content_type: str,
    *,
    team_id: str,
) -> dict:
    return save_local_file_from_path(
        file_path,
        team_id=team_id,
        filename=filename,
        content_type=content_type,
    )


def upload_path_to_r2(file_path: Path, filename: str, content_type: str, *, prefix: str) -> dict:
    size = int(file_path.stat().st_size)
    if size > MAX_UPLOAD_BYTES:
        raise HTTPException(
            status_code=413,
            detail=f"视频过大，最大允许 {MAX_UPLOAD_BYTES // (1024 * 1024)} MB",
        )
    with file_path.open("rb") as fh:
        result = upload_fileobj(fh, filename, content_type, prefix=prefix)
    return {**result, "filename": filename, "size_bytes": size}


async def _download_public_url_to_temp(url: str, suffix: str = ".mp4") -> Path:
    timeout = httpx.Timeout(float(settings.llm_http_timeout), connect=30.0)
    with tempfile.NamedTemporaryFile(suffix=suffix, delete=False) as tmp:
        tmp_path = Path(tmp.name)
    try:
        async with httpx.AsyncClient(timeout=timeout, follow_redirects=True) as client:
            async with client.stream("GET", url) as resp:
                if resp.status_code >= 400:
                    raise HTTPException(
                        status_code=502,
                        detail=f"拉取视频失败 HTTP {resp.status_code}",
                    )
                written = 0
                with tmp_path.open("wb") as out:
                    async for chunk in resp.aiter_bytes(1024 * 1024):
                        written += len(chunk)
                        if written > MAX_UPLOAD_BYTES:
                            raise HTTPException(
                                status_code=413,
                                detail=f"视频过大，最大允许 {MAX_UPLOAD_BYTES // (1024 * 1024)} MB",
                            )
                        out.write(chunk)
        return tmp_path
    except Exception:
        try:
            tmp_path.unlink(missing_ok=True)
        except Exception:
            pass
        raise


async def rehost_studio_video(
    db: Session,
    user: User,
    source_url: str,
    *,
    prefix: str,
    allow_external_pass_through: bool = False,
    team_id: str | None = None,
) -> dict:
    """
    Rehost studio media to R2 under ``prefix``.

    Returns dict with public_url, key, content_type, filename, size_bytes, rehosted.
    """
    raw = (source_url or "").strip()
    if not raw:
        raise HTTPException(status_code=400, detail="缺少 source_url")

    if is_r2_public_asset_url(raw):
        key = key_from_r2_public_url(raw)
        filename = Path(key or "video.mp4").name
        return {
            "public_url": raw.split("?")[0],
            "key": key,
            "content_type": _video_content_type(filename),
            "filename": filename,
            "size_bytes": 0,
            "rehosted": False,
        }

    media = parse_studio_media_url(raw)
    if media is None:
        if allow_external_pass_through and (
            raw.startswith("http://") or raw.startswith("https://")
        ):
            return {
                "public_url": raw,
                "key": None,
                "content_type": "video/mp4",
                "filename": "video.mp4",
                "size_bytes": 0,
                "rehosted": False,
            }
        raise HTTPException(status_code=400, detail="无法识别的视频地址")

    use_local_team = prefix == "team" and resolve_backend("team") == "local"
    if use_local_team and not (team_id or "").strip():
        raise HTTPException(status_code=400, detail="本地团队存储需要 team_id")

    if not use_local_team and (
        not is_r2_configured() or not (settings.r2_public_url or "").strip()
    ):
        raise HTTPException(status_code=503, detail="R2 未配置，无法转存生成历史视频")

    def _store_path(local_file: Path, name: str, ctype: str) -> dict:
        if use_local_team:
            saved = upload_path_to_local(
                local_file, name, ctype, team_id=str(team_id).strip()
            )
            return {
                **saved,
                "public_url": None,
                "rehosted": True,
                "storage_backend": "local",
            }
        result = upload_path_to_r2(local_file, name, ctype, prefix=prefix)
        return {**result, "rehosted": True, "storage_backend": "r2"}

    try:
        if media["kind"] == "upload":
            safe_rel = sanitize_upload_rel_path(media["rel_path"])
            if not user_can_access_upload(db, user, safe_rel):
                raise HTTPException(status_code=403, detail="无权访问该视频")
            file_path = (_UPLOAD_ROOT / safe_rel).resolve()
            root = _UPLOAD_ROOT.resolve()
            if not str(file_path).startswith(str(root)) or not file_path.is_file():
                raise HTTPException(status_code=404, detail="视频文件不存在")
            filename = file_path.name
            ctype = _video_content_type(filename)
            return _store_path(file_path, filename, ctype)

        safe_name = sanitize_filename(media["filename"])
        safe_subfolder = (media.get("subfolder") or "").strip().replace("\\", "/").strip("/")
        if safe_subfolder and not all(
            part and part not in (".", "..") for part in safe_subfolder.split("/")
        ):
            raise HTTPException(status_code=400, detail="非法 subfolder")
        if not user_can_access_comfy_output(
            db, user, safe_name, subfolder=safe_subfolder
        ):
            raise HTTPException(status_code=403, detail="无权访问该视频")

        local_path = _resolve_comfy_output_path(safe_name, safe_subfolder)
        if local_path and local_path.is_file():
            ctype = _video_content_type(safe_name)
            return _store_path(local_path, safe_name, ctype)

        params = {"filename": safe_name, "type": media.get("type") or "output"}
        if safe_subfolder:
            params["subfolder"] = safe_subfolder
        parsed_src = urlparse(raw or "")
        node_hint = None
        if parsed_src.query:
            node_hint = (parse_qs(parsed_src.query).get("node") or [None])[0]
        upstream = f"{resolve_comfyui_node_url(node_hint)}/view"
        timeout = httpx.Timeout(float(settings.llm_http_timeout), connect=30.0)
        suffix = Path(safe_name).suffix or ".mp4"
        with tempfile.NamedTemporaryFile(suffix=suffix, delete=False) as tmp:
            tmp_path = Path(tmp.name)
        try:
            async with httpx.AsyncClient(timeout=timeout) as client:
                async with client.stream("GET", upstream, params=params) as resp:
                    if resp.status_code >= 400:
                        raise HTTPException(
                            status_code=502,
                            detail=f"拉取生成视频失败 HTTP {resp.status_code}",
                        )
                    written = 0
                    with tmp_path.open("wb") as out:
                        async for chunk in resp.aiter_bytes(1024 * 1024):
                            written += len(chunk)
                            if written > MAX_UPLOAD_BYTES:
                                raise HTTPException(
                                    status_code=413,
                                    detail=f"视频过大，最大允许 {MAX_UPLOAD_BYTES // (1024 * 1024)} MB",
                                )
                            out.write(chunk)
            ctype = _video_content_type(safe_name)
            return _store_path(tmp_path, safe_name, ctype)
        finally:
            try:
                tmp_path.unlink(missing_ok=True)
            except Exception:
                pass
    except HTTPException:
        raise
    except R2NotConfiguredError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    except RuntimeError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc
    except httpx.HTTPError as exc:
        raise HTTPException(status_code=502, detail=f"拉取生成视频失败: {exc}") from exc


async def copy_r2_public_video_to_prefix(
    source_url: str,
    *,
    prefix: str,
    team_id: str | None = None,
) -> dict:
    """Download an R2 public asset and re-upload under team local disk or R2 prefix."""
    use_local_team = prefix == "team" and resolve_backend("team") == "local"
    if use_local_team:
        if not (team_id or "").strip():
            raise HTTPException(status_code=400, detail="本地团队存储需要 team_id")
    elif not is_r2_configured() or not (settings.r2_public_url or "").strip():
        raise HTTPException(status_code=503, detail="R2 未配置，无法转存视频")
    key = key_from_r2_public_url(source_url)
    if not key:
        raise HTTPException(status_code=400, detail="无法识别的 R2 地址")
    filename = Path(key).name or "video.mp4"
    suffix = Path(filename).suffix or ".mp4"
    tmp_path = await _download_public_url_to_temp(source_url.split("?")[0], suffix=suffix)
    try:
        ctype = _video_content_type(filename)
        if use_local_team:
            saved = upload_path_to_local(
                tmp_path, filename, ctype, team_id=str(team_id).strip()
            )
            return {**saved, "rehosted": True, "storage_backend": "local"}
        result = upload_path_to_r2(tmp_path, filename, ctype, prefix=prefix)
        return {**result, "rehosted": True, "storage_backend": "r2"}
    finally:
        try:
            tmp_path.unlink(missing_ok=True)
        except Exception:
            pass
