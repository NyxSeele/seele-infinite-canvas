from datetime import datetime

import httpx
from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import FileResponse, RedirectResponse, Response, StreamingResponse
from sqlalchemy.orm import Session

from core.config import settings
from core.dependencies import get_media_user, require_admin
from db.session import get_db
from models import User
from schemas.admin import AdminFileListResponse, AdminFileStatsResponse
from services.admin_files_service import (
    admin_files_stats,
    get_admin_file_thumbnail_bytes,
    list_admin_files,
    resolve_admin_file_local_path,
    resolve_admin_file_remote_url,
)

router = APIRouter(prefix="/api/admin/files", tags=["admin-files"])


@router.get("", response_model=AdminFileListResponse)
def list_files(
    page: int = Query(1, ge=1),
    page_size: int = Query(50, ge=1, le=100),
    source: str | None = Query(None, description="upload|r2|generation|asset|export"),
    user_id: int | None = Query(None),
    category: str | None = Query(None, description="image|video|audio|document|other|all"),
    q: str | None = Query(None, description="搜索文件名或提示词"),
    since: datetime | None = Query(None),
    until: datetime | None = Query(None),
    admin: User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    return list_admin_files(
        db,
        admin_user_id=admin.id,
        page=page,
        page_size=page_size,
        source=source,
        user_id=user_id,
        category=category,
        q=q,
        since=since,
        until=until,
    )


@router.get("/stats", response_model=AdminFileStatsResponse)
def file_stats(
    _: User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    return admin_files_stats(db)


@router.get("/{file_id}/thumbnail")
async def file_thumbnail(
    file_id: str,
    user: User = Depends(get_media_user),
    db: Session = Depends(get_db),
):
    if user.role != "admin":
        raise HTTPException(status_code=403, detail="需要管理员权限")
    data = await get_admin_file_thumbnail_bytes(file_id, db)
    return Response(
        content=data,
        media_type="image/jpeg",
        headers={"Cache-Control": "private, max-age=86400"},
    )


@router.get("/{file_id}/download")
async def download_file(
    file_id: str,
    _: User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    try:
        path, filename = resolve_admin_file_local_path(file_id, db)
        return FileResponse(path, filename=filename)
    except HTTPException as exc:
        if exc.status_code != 404:
            raise
        detail = str(exc.detail or "")
        if "媒体代理" not in detail and "预签名" not in detail and "外链" not in detail:
            raise

    remote_url, filename = resolve_admin_file_remote_url(file_id, db)
    if remote_url.startswith(("http://", "https://")) and "127.0.0.1" not in remote_url:
        return RedirectResponse(remote_url, status_code=307)

    timeout = httpx.Timeout(float(settings.llm_http_timeout), connect=30.0)
    async with httpx.AsyncClient(timeout=timeout, follow_redirects=True) as client:
        resp = await client.get(remote_url)
        if resp.status_code >= 400:
            raise HTTPException(status_code=502, detail="上游文件下载失败")
        media_type = resp.headers.get("content-type", "application/octet-stream")
        headers = {}
        if filename:
            headers["Content-Disposition"] = f'attachment; filename="{filename}"'
        return StreamingResponse(
            iter([resp.content]),
            media_type=media_type,
            headers=headers,
        )
