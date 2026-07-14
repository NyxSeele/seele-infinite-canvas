"""Admin 用户文件聚合：上传、R2、生成结果、资产库、导出。"""

from __future__ import annotations

from datetime import datetime
from pathlib import Path
from typing import Any
from urllib.parse import parse_qs, urlparse

import httpx
from fastapi import HTTPException
from sqlalchemy.orm import Session

from core.config import settings
from core.datetime_utils import to_utc_iso
from models import ExportJob, Task, User, UserAsset, UserUpload
from models.r2_file import R2File
from services.media_access import (
    append_media_ticket,
    grant_output_access,
    issue_media_ticket,
    normalize_media_reference_url,
)
from services.r2 import (
    R2NotConfiguredError,
    generate_presigned_download_url,
    r2_public_url_for_key,
)

_UPLOAD_ROOT = Path("uploads")

_DOC_EXTS = {
    ".pdf",
    ".doc",
    ".docx",
    ".xls",
    ".xlsx",
    ".ppt",
    ".pptx",
    ".txt",
    ".md",
    ".csv",
}

SOURCE_LABELS = {
    "upload": "本地上传",
    "r2": "团队文件",
    "generation": "AI 生成",
    "asset": "资产库",
    "export": "剧本导出",
}

MAX_PER_SOURCE = 3000


def file_category(content_type: str | None, filename: str | None) -> str:
    ct = (content_type or "").lower().strip()
    name = (filename or "").lower()
    if ct.startswith("image/"):
        return "image"
    if ct.startswith("video/"):
        return "video"
    if ct.startswith("audio/"):
        return "audio"
    ext = ""
    if "." in name:
        ext = "." + name.rsplit(".", 1)[-1]
    if ext in {".png", ".jpg", ".jpeg", ".gif", ".webp", ".bmp", ".svg"}:
        return "image"
    if ext in {".mp4", ".mov", ".webm", ".mkv", ".avi", ".m4v"}:
        return "video"
    if ext in {".mp3", ".wav", ".aac", ".flac", ".m4a", ".ogg"}:
        return "audio"
    if ext in _DOC_EXTS or ct in {
        "application/pdf",
        "application/msword",
        "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    }:
        return "document"
    if ext == ".zip":
        return "document"
    return "other"


def _filename_from_url(url: str | None) -> str:
    if not url:
        return "unknown"
    text = (url or "").strip()
    if "/api/view" in text:
        parsed = urlparse(text)
        qs = parse_qs(parsed.query)
        names = qs.get("filename") or []
        if names and names[0]:
            return names[0]
    raw = text.split("?")[0].rstrip("/")
    if "/" in raw:
        return raw.rsplit("/", 1)[-1] or "unknown"
    return raw or "unknown"


def _local_file_size(rel_path: str | None) -> int | None:
    if not rel_path:
        return None
    try:
        full = (_UPLOAD_ROOT / rel_path).resolve()
        root = _UPLOAD_ROOT.resolve()
        if str(full).startswith(str(root)) and full.is_file():
            return full.stat().st_size
    except OSError:
        pass
    return None


def _r2_public_url(key: str) -> str | None:
    try:
        if (settings.r2_public_url or "").strip():
            return r2_public_url_for_key(key)
    except R2NotConfiguredError:
        return None
    return None


def _in_range(dt: datetime | None, since: datetime | None, until: datetime | None) -> bool:
    if dt is None:
        return since is None and until is None
    if since and dt < since:
        return False
    if until and dt > until:
        return False
    return True


def _matches_q(text: str | None, q: str | None) -> bool:
    if not q:
        return True
    return q.lower() in (text or "").lower()


def _fetch_uploads(
    db: Session,
    *,
    user_id: int | None,
    q: str | None,
    since: datetime | None,
    until: datetime | None,
) -> list[dict[str, Any]]:
    query = db.query(UserUpload, User).join(User, UserUpload.user_id == User.id)
    if user_id is not None:
        query = query.filter(UserUpload.user_id == user_id)
    if since is not None:
        query = query.filter(UserUpload.created_at >= since)
    if until is not None:
        query = query.filter(UserUpload.created_at <= until)
    if q:
        term = f"%{q.strip()}%"
        query = query.filter(UserUpload.path.ilike(term))
    rows = (
        query.order_by(UserUpload.created_at.desc()).limit(MAX_PER_SOURCE).all()
    )
    items: list[dict[str, Any]] = []
    for row, user in rows:
        filename = _filename_from_url(row.path)
        items.append(
            {
                "id": f"upload:{row.id}",
                "source": "upload",
                "source_id": str(row.id),
                "user_id": row.user_id,
                "username": user.username,
                "filename": filename,
                "category": file_category(None, filename),
                "content_type": None,
                "size_bytes": _local_file_size(row.path),
                "url": f"/api/uploads/{row.path}",
                "created_at": to_utc_iso(row.created_at),
                "description": None,
                "meta": {"path": row.path},
            }
        )
    return items


def _fetch_r2_files(
    db: Session,
    *,
    user_id: int | None,
    q: str | None,
    since: datetime | None,
    until: datetime | None,
) -> list[dict[str, Any]]:
    query = db.query(R2File, User).join(User, R2File.uploader_id == User.id)
    if user_id is not None:
        query = query.filter(R2File.uploader_id == user_id)
    if since is not None:
        query = query.filter(R2File.uploaded_at >= since)
    if until is not None:
        query = query.filter(R2File.uploaded_at <= until)
    if q:
        term = f"%{q.strip()}%"
        query = query.filter(R2File.filename.ilike(term))
    rows = query.order_by(R2File.uploaded_at.desc()).limit(MAX_PER_SOURCE).all()
    items: list[dict[str, Any]] = []
    for row, user in rows:
        items.append(
            {
                "id": f"r2:{row.id}",
                "source": "r2",
                "source_id": str(row.id),
                "user_id": row.uploader_id,
                "username": user.username,
                "filename": row.filename,
                "category": file_category(row.content_type, row.filename),
                "content_type": row.content_type,
                "size_bytes": row.size_bytes,
                "url": _r2_public_url(row.key) or f"/api/r2/files/{row.id}/download",
                "created_at": to_utc_iso(row.uploaded_at),
                "description": row.description,
                "meta": {"key": row.key},
            }
        )
    return items


def _fetch_generations(
    db: Session,
    *,
    user_id: int | None,
    q: str | None,
    since: datetime | None,
    until: datetime | None,
) -> list[dict[str, Any]]:
    query = (
        db.query(Task, User)
        .outerjoin(User, Task.user_id == User.id)
        .filter(Task.result.isnot(None), Task.result != "")
    )
    if user_id is not None:
        query = query.filter(Task.user_id == user_id)
    if since is not None:
        query = query.filter(Task.completed_at >= since)
    if until is not None:
        query = query.filter(Task.completed_at <= until)
    rows = (
        query.order_by(Task.completed_at.desc().nullslast(), Task.created_at.desc())
        .limit(MAX_PER_SOURCE)
        .all()
    )
    items: list[dict[str, Any]] = []
    for task, user in rows:
        filename = _filename_from_url(task.result)
        if q and not _matches_q(filename, q) and not _matches_q(task.prompt_text, q):
            continue
        if not _in_range(task.completed_at or task.created_at, since, until):
            continue
        cat = file_category(None, filename)
        if task.task_type in ("video", "image") and cat == "other":
            cat = task.task_type
        items.append(
            {
                "id": f"generation:{task.id}",
                "source": "generation",
                "source_id": task.id,
                "user_id": task.user_id,
                "username": user.username if user else None,
                "filename": filename,
                "category": cat,
                "content_type": None,
                "size_bytes": None,
                "url": task.result,
                "created_at": to_utc_iso(task.completed_at or task.created_at),
                "description": (task.prompt_text or "")[:200] or None,
                "meta": {
                    "task_type": task.task_type,
                    "status": task.status,
                    "model_id": task.model_id,
                },
            }
        )
    return items


def _fetch_assets(
    db: Session,
    *,
    user_id: int | None,
    q: str | None,
    since: datetime | None,
    until: datetime | None,
) -> list[dict[str, Any]]:
    query = db.query(UserAsset, User).join(User, UserAsset.user_id == User.id)
    if user_id is not None:
        query = query.filter(UserAsset.user_id == user_id)
    if since is not None:
        query = query.filter(UserAsset.created_at >= since)
    if until is not None:
        query = query.filter(UserAsset.created_at <= until)
    if q:
        term = f"%{q.strip()}%"
        query = query.filter(
            (UserAsset.name.ilike(term)) | (UserAsset.image_url.ilike(term))
        )
    rows = query.order_by(UserAsset.created_at.desc()).limit(MAX_PER_SOURCE).all()
    items: list[dict[str, Any]] = []
    for row, user in rows:
        filename = row.name or _filename_from_url(row.image_url)
        items.append(
            {
                "id": f"asset:{row.id}",
                "source": "asset",
                "source_id": row.id,
                "user_id": row.user_id,
                "username": user.username,
                "filename": filename,
                "category": file_category(None, _filename_from_url(row.image_url)),
                "content_type": None,
                "size_bytes": None,
                "url": row.image_url,
                "created_at": to_utc_iso(row.created_at),
                "description": row.note,
                "meta": {
                    "kind": row.kind,
                    "source_canvas_name": row.source_canvas_name,
                },
            }
        )
    return items


def _fetch_exports(
    db: Session,
    *,
    user_id: int | None,
    q: str | None,
    since: datetime | None,
    until: datetime | None,
) -> list[dict[str, Any]]:
    query = (
        db.query(ExportJob, User)
        .join(User, ExportJob.created_by == User.id)
        .filter(ExportJob.file_path.isnot(None), ExportJob.file_path != "")
    )
    if user_id is not None:
        query = query.filter(ExportJob.created_by == user_id)
    if since is not None:
        query = query.filter(ExportJob.created_at >= since)
    if until is not None:
        query = query.filter(ExportJob.created_at <= until)
    rows = query.order_by(ExportJob.created_at.desc()).limit(MAX_PER_SOURCE).all()
    items: list[dict[str, Any]] = []
    for row, user in rows:
        filename = _filename_from_url(row.file_path)
        if q and not _matches_q(filename, q):
            continue
        items.append(
            {
                "id": f"export:{row.id}",
                "source": "export",
                "source_id": row.id,
                "user_id": row.created_by,
                "username": user.username,
                "filename": filename,
                "category": file_category(None, filename),
                "content_type": "application/zip",
                "size_bytes": _local_file_size(row.file_path),
                "url": f"/api/exports/{row.id}/download",
                "created_at": to_utc_iso(row.created_at),
                "description": f"项目 {row.project_id[:8]}…",
                "meta": {"project_id": row.project_id, "status": row.status},
            }
        )
    return items


_SOURCE_FETCHERS = {
    "upload": _fetch_uploads,
    "r2": _fetch_r2_files,
    "generation": _fetch_generations,
    "asset": _fetch_assets,
    "export": _fetch_exports,
}

_R2_PRESIGN_EXPIRES = 3600


def admin_media_url(raw: str | None, admin_user_id: int) -> str | None:
    """为 admin 预览附加 output grant + 媒体票据（先剥离旧 mt）。"""
    text = (raw or "").strip()
    if not text:
        return None
    if text.startswith("http://") or text.startswith("https://"):
        if "/api/view" not in text and "/api/uploads/" not in text:
            return text
        text = normalize_media_reference_url(text)
        if text.startswith("http://") or text.startswith("https://"):
            from urllib.parse import urlparse

            parsed = urlparse(text)
            text = f"{parsed.path}?{parsed.query}" if parsed.query else parsed.path
    path = normalize_media_reference_url(text)
    if not path.startswith("/"):
        path = f"/{path}"
    if "/api/view" in path:
        grant_output_access(admin_user_id, path)
    ticket = issue_media_ticket(admin_user_id)["media_ticket"]
    return append_media_ticket(path, ticket)


def _r2_presigned_url(key: str | None) -> str | None:
    if not key:
        return None
    try:
        return generate_presigned_download_url(key, expires=_R2_PRESIGN_EXPIRES)
    except (R2NotConfiguredError, RuntimeError):
        return None


def enrich_admin_file_item(item: dict[str, Any], admin_user_id: int) -> dict[str, Any]:
    source = item.get("source") or ""
    raw_url = (item.get("url") or "").strip()
    file_id = item.get("id") or ""
    download_url = f"/api/admin/files/{file_id}/download"

    preview_url: str | None = None
    thumbnail_url: str | None = None
    if source == "r2":
        key = (item.get("meta") or {}).get("key")
        preview_url = _r2_public_url(key) if key else None
        if not preview_url:
            preview_url = _r2_presigned_url(key)
    else:
        preview_url = admin_media_url(raw_url, admin_user_id)
        if not preview_url and raw_url.startswith(("http://", "https://")):
            preview_url = raw_url

    item["preview_url"] = preview_url
    item["download_url"] = download_url
    if item.get("category") == "video":
        ticket = issue_media_ticket(admin_user_id)["media_ticket"]
        item["thumbnail_url"] = append_media_ticket(
            f"/api/admin/files/{file_id}/thumbnail", ticket
        )
    return item


def parse_admin_file_id(file_id: str) -> tuple[str, str]:
    if ":" not in file_id:
        raise HTTPException(status_code=400, detail="非法文件 ID")
    source, source_id = file_id.split(":", 1)
    if source not in _SOURCE_FETCHERS or not source_id:
        raise HTTPException(status_code=400, detail="非法文件 ID")
    return source, source_id


def resolve_admin_upload_path(rel_path: str) -> Path:
    full = (_UPLOAD_ROOT / rel_path).resolve()
    root = _UPLOAD_ROOT.resolve()
    if not str(full).startswith(str(root)) or not full.is_file():
        raise HTTPException(status_code=404, detail="文件不存在")
    return full


def _upload_rel_from_url(url: str) -> str | None:
    raw = (url or "").strip()
    if not raw:
        return None
    if raw.startswith("/api/uploads/"):
        return raw[len("/api/uploads/") :]
    if not raw.startswith("/") and not raw.startswith("http"):
        return raw.lstrip("/")
    return None


def resolve_admin_file_local_path(file_id: str, db: Session) -> tuple[Path, str]:
    """返回 (本地路径, 下载文件名)。"""
    source, source_id = parse_admin_file_id(file_id)

    if source == "upload":
        row = db.get(UserUpload, int(source_id))
        if not row:
            raise HTTPException(status_code=404, detail="文件不存在")
        return resolve_admin_upload_path(row.path), _filename_from_url(row.path)

    if source == "export":
        job = db.get(ExportJob, source_id)
        if not job or not job.file_path:
            raise HTTPException(status_code=404, detail="导出文件不存在")
        return resolve_admin_upload_path(job.file_path), _filename_from_url(job.file_path)

    if source == "generation":
        task = db.get(Task, source_id)
        if not task or not task.result:
            raise HTTPException(status_code=404, detail="生成结果不存在")
        rel = _upload_rel_from_url(task.result)
        if rel:
            return resolve_admin_upload_path(rel), _filename_from_url(task.result)
        raise HTTPException(status_code=404, detail="该生成结果需通过媒体代理下载")

    if source == "asset":
        row = db.get(UserAsset, source_id)
        if not row:
            raise HTTPException(status_code=404, detail="资产不存在")
        image_url = (row.image_url or "").strip()
        rel = _upload_rel_from_url(image_url)
        if rel:
            return resolve_admin_upload_path(rel), row.name or _filename_from_url(image_url)
        raise HTTPException(status_code=404, detail="该资产需通过外链或媒体代理下载")

    if source == "r2":
        row = db.get(R2File, int(source_id))
        if not row:
            raise HTTPException(status_code=404, detail="R2 文件不存在")
        raise HTTPException(status_code=404, detail="R2 文件请使用预签名链接下载")

    raise HTTPException(status_code=400, detail="不支持的文件类型")


def resolve_admin_file_remote_url(file_id: str, db: Session) -> tuple[str, str]:
    """返回 (远程 URL, 下载文件名) — 用于 R2 / 外链 / Comfy 代理。"""
    source, source_id = parse_admin_file_id(file_id)

    if source == "r2":
        row = db.get(R2File, int(source_id))
        if not row:
            raise HTTPException(status_code=404, detail="R2 文件不存在")
        url = _r2_public_url(row.key) or _r2_presigned_url(row.key)
        if not url:
            raise HTTPException(status_code=503, detail="R2 下载链接不可用")
        return url, row.filename

    if source == "asset":
        row = db.get(UserAsset, source_id)
        if not row:
            raise HTTPException(status_code=404, detail="资产不存在")
        image_url = (row.image_url or "").strip()
        if image_url.startswith(("http://", "https://")):
            return image_url, row.name or _filename_from_url(image_url)
        raise HTTPException(status_code=404, detail="资产文件不可直接下载")

    if source == "generation":
        task = db.get(Task, source_id)
        if not task or not task.result:
            raise HTTPException(status_code=404, detail="生成结果不存在")
        result = task.result.strip()
        if result.startswith(("http://", "https://")):
            return result, _filename_from_url(result)
        if "/api/view" in result:
            parsed = urlparse(result)
            qs = parse_qs(parsed.query)
            filename = (qs.get("filename") or [""])[0]
            if not filename:
                raise HTTPException(status_code=404, detail="无法解析生成结果")
            file_type = (qs.get("type") or ["output"])[0]
            subfolder = (qs.get("subfolder") or [""])[0]
            node = (qs.get("node") or [None])[0]
            from core.comfyui_settings import resolve_comfyui_node_url
            from urllib.parse import urlencode

            params = {"filename": filename, "type": file_type}
            if subfolder:
                params["subfolder"] = subfolder
            base = resolve_comfyui_node_url(node)
            return f"{base}/view?{urlencode(params)}", filename

    raise HTTPException(status_code=404, detail="文件不可远程下载")


_THUMB_CACHE = _UPLOAD_ROOT / ".admin_thumbs"


def _thumb_cache_path(file_id: str) -> Path:
    safe = file_id.replace(":", "_").replace("/", "_")
    return _THUMB_CACHE / f"{safe}.jpg"


async def fetch_admin_file_bytes(file_id: str, db: Session) -> bytes:
    """读取文件二进制（本地或远程代理）。"""
    try:
        path, _ = resolve_admin_file_local_path(file_id, db)
        return path.read_bytes()
    except HTTPException as exc:
        if exc.status_code != 404:
            raise
        detail = str(exc.detail or "")
        if "媒体代理" not in detail and "预签名" not in detail and "外链" not in detail:
            raise

    remote_url, _ = resolve_admin_file_remote_url(file_id, db)
    timeout = httpx.Timeout(float(settings.llm_http_timeout), connect=30.0)
    async with httpx.AsyncClient(timeout=timeout, follow_redirects=True) as client:
        resp = await client.get(remote_url)
        if resp.status_code >= 400:
            raise HTTPException(status_code=502, detail="上游文件读取失败")
        return resp.content


async def get_admin_file_thumbnail_bytes(file_id: str, db: Session) -> bytes:
    cache = _thumb_cache_path(file_id)
    if cache.is_file():
        return cache.read_bytes()

    from services.feedback_vision import _extract_video_frame

    raw = await fetch_admin_file_bytes(file_id, db)
    extracted = _extract_video_frame(raw)
    if not extracted:
        raise HTTPException(status_code=404, detail="无法生成视频缩略图")
    data, _mime = extracted
    _THUMB_CACHE.mkdir(parents=True, exist_ok=True)
    cache.write_bytes(data)
    return data


def list_admin_files(
    db: Session,
    *,
    admin_user_id: int | None = None,
    page: int = 1,
    page_size: int = 50,
    source: str | None = None,
    user_id: int | None = None,
    category: str | None = None,
    q: str | None = None,
    since: datetime | None = None,
    until: datetime | None = None,
) -> dict[str, Any]:
    page = max(1, page)
    page_size = max(1, min(page_size, 100))
    q_norm = q.strip() if q else None

    sources = [source] if source and source in _SOURCE_FETCHERS else list(_SOURCE_FETCHERS)
    items: list[dict[str, Any]] = []
    for src in sources:
        items.extend(
            _SOURCE_FETCHERS[src](
                db,
                user_id=user_id,
                q=q_norm,
                since=since,
                until=until,
            )
        )

    if category and category.strip() and category != "all":
        cat = category.strip()
        items = [i for i in items if i.get("category") == cat]

    items.sort(key=lambda x: x.get("created_at") or "", reverse=True)
    total = len(items)
    start = (page - 1) * page_size
    page_items = items[start : start + page_size]
    if admin_user_id is not None:
        page_items = [
            enrich_admin_file_item(dict(item), admin_user_id) for item in page_items
        ]

    return {
        "items": page_items,
        "total": total,
        "page": page,
        "page_size": page_size,
    }


def admin_files_stats(db: Session) -> dict[str, Any]:
    by_source = {
        "upload": db.query(UserUpload.id).count(),
        "r2": db.query(R2File.id).count(),
        "generation": db.query(Task.id).filter(Task.result.isnot(None), Task.result != "").count(),
        "asset": db.query(UserAsset.id).count(),
        "export": db.query(ExportJob.id).filter(
            ExportJob.file_path.isnot(None), ExportJob.file_path != ""
        ).count(),
    }
    total = sum(by_source.values())

    upload_bytes = 0
    for row in db.query(UserUpload.path).all():
        size = _local_file_size(row.path)
        if size:
            upload_bytes += size

    r2_bytes = db.query(R2File.size_bytes).all()
    r2_total = sum(int(r[0] or 0) for r in r2_bytes)

    return {
        "total": total,
        "by_source": by_source,
        "storage_bytes": {
            "upload": upload_bytes,
            "r2": r2_total,
        },
    }
