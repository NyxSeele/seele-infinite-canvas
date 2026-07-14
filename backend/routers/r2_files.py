"""Team file space backed by Cloudflare R2 + r2_files metadata."""

from __future__ import annotations

from fastapi import APIRouter, Depends, File, Form, HTTPException, Query, UploadFile
from sqlalchemy.orm import Session

from core.dependencies import require_admin, require_r2_access
from core.config import settings
from db.session import get_db
from models import User
from models.r2_file import R2File
from models.team import Team
from models.user_asset import UserAsset, new_asset_id
from schemas.assets import AssetOut
from schemas.r2_files import (
    AddToAssetsRequest,
    DownloadUrlResponse,
    FileRegisterRequest,
    PresignUploadRequest,
    PresignUploadResponse,
    R2FileListResponse,
    R2FileOut,
)
from services.media_access import append_media_ticket, issue_media_ticket
from services.r2 import (
    R2NotConfiguredError,
    delete_file,
    generate_presigned_download_url,
    generate_presigned_upload_url,
    is_r2_configured,
    r2_public_url_for_key,
    upload_fileobj,
)
from services.team_service import require_team_editor

router = APIRouter(prefix="/api/r2", tags=["r2-files"])

KEY_PREFIX = "team/"
PRESIGN_EXPIRES = 3600
MAX_UPLOAD_BYTES = 2 * 1024 * 1024 * 1024

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


def _ensure_r2() -> None:
    if not is_r2_configured():
        raise HTTPException(status_code=503, detail="R2 未配置")


def _file_category(content_type: str, filename: str) -> str:
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
    return "other"


def _to_out(row: R2File) -> R2FileOut:
    public_url = None
    try:
        if (settings.r2_public_url or "").strip():
            public_url = r2_public_url_for_key(row.key)
    except R2NotConfiguredError:
        public_url = None
    return R2FileOut(
        id=row.id,
        key=row.key,
        filename=row.filename,
        content_type=row.content_type,
        size_bytes=row.size_bytes,
        uploader_id=row.uploader_id,
        uploader_name=row.uploader_name,
        uploaded_at=row.uploaded_at,
        description=row.description,
        category=_file_category(row.content_type, row.filename),
        public_url=public_url,
    )


@router.get("/files", response_model=R2FileListResponse)
def list_r2_files(
    q: str | None = Query(None),
    limit: int = Query(100, ge=1, le=500),
    _: User = Depends(require_r2_access),
    db: Session = Depends(get_db),
):
    query = db.query(R2File)
    if q and q.strip():
        term = f"%{q.strip()}%"
        query = query.filter(R2File.filename.ilike(term))
    total = query.count()
    rows = (
        query.order_by(R2File.uploaded_at.desc()).limit(limit).all()
    )
    return R2FileListResponse(items=[_to_out(r) for r in rows], total=total)


@router.post("/presign-upload", response_model=PresignUploadResponse)
def presign_upload(
    body: PresignUploadRequest,
    _: User = Depends(require_r2_access),
):
    _ensure_r2()
    try:
        result = generate_presigned_upload_url(
            body.filename,
            body.content_type,
            expires=PRESIGN_EXPIRES,
        )
    except R2NotConfiguredError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    except RuntimeError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc
    return PresignUploadResponse(
        upload_url=result["url"],
        key=result["key"],
        content_type=result["content_type"],
        expires_in=PRESIGN_EXPIRES,
    )


@router.post("/upload", response_model=R2FileOut)
async def upload_and_register_file(
    file: UploadFile = File(...),
    description: str | None = Form(None),
    current_user: User = Depends(require_r2_access),
    db: Session = Depends(get_db),
):
    """Same-origin multipart upload → R2 + DB register (avoids browser CORS)."""
    _ensure_r2()
    filename = (file.filename or "file").strip() or "file"
    content_type = (file.content_type or "application/octet-stream").strip()
    try:
        file.file.seek(0, 2)
        size = int(file.file.tell() or 0)
        file.file.seek(0)
    except Exception:
        size = 0
    if size > MAX_UPLOAD_BYTES:
        raise HTTPException(
            status_code=413,
            detail=f"文件过大，最大允许 {MAX_UPLOAD_BYTES // (1024 * 1024)} MB",
        )
    try:
        result = upload_fileobj(
            file.file,
            filename,
            content_type,
            prefix="team",
        )
    except R2NotConfiguredError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    except RuntimeError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc

    uploader_name = (
        (current_user.display_name or "").strip()
        or current_user.username
    )
    row = R2File(
        key=result["key"],
        filename=filename,
        content_type=result["content_type"],
        size_bytes=size,
        uploader_id=current_user.id,
        uploader_name=uploader_name[:64],
        description=(description or "").strip() or None,
    )
    db.add(row)
    db.commit()
    db.refresh(row)
    return _to_out(row)


@router.post("/files", response_model=R2FileOut)
def register_file(
    body: FileRegisterRequest,
    current_user: User = Depends(require_r2_access),
    db: Session = Depends(get_db),
):
    key = body.key.strip()
    if not key.startswith(KEY_PREFIX):
        raise HTTPException(status_code=400, detail="非法文件 key")
    existing = db.query(R2File).filter(R2File.key == key).first()
    if existing:
        raise HTTPException(status_code=409, detail="文件已登记")

    uploader_name = (
        (current_user.display_name or "").strip()
        or current_user.username
    )
    row = R2File(
        key=key,
        filename=body.filename.strip(),
        content_type=body.content_type.strip() or "application/octet-stream",
        size_bytes=int(body.size_bytes),
        uploader_id=current_user.id,
        uploader_name=uploader_name[:64],
        description=(body.description or "").strip() or None,
    )
    db.add(row)
    db.commit()
    db.refresh(row)
    return _to_out(row)


@router.get("/files/{file_id}/download", response_model=DownloadUrlResponse)
def download_file(
    file_id: int,
    _: User = Depends(require_r2_access),
    db: Session = Depends(get_db),
):
    _ensure_r2()
    row = db.get(R2File, file_id)
    if not row:
        raise HTTPException(status_code=404, detail="文件不存在")
    try:
        url = generate_presigned_download_url(row.key, expires=PRESIGN_EXPIRES)
    except R2NotConfiguredError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    except RuntimeError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc
    return DownloadUrlResponse(download_url=url, expires_in=PRESIGN_EXPIRES)


@router.delete("/files/{file_id}")
def delete_r2_file(
    file_id: int,
    _: User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    row = db.get(R2File, file_id)
    if not row:
        raise HTTPException(status_code=404, detail="文件不存在")
    key = row.key
    db.delete(row)
    db.commit()
    if is_r2_configured():
        try:
            delete_file(key)
        except Exception:
            # DB 已删；R2 删除失败不回滚（避免幽灵登记）
            pass
    return {"ok": True, "id": file_id}


@router.post("/files/{file_id}/add-to-assets", response_model=AssetOut)
def add_r2_file_to_assets(
    file_id: int,
    body: AddToAssetsRequest,
    current_user: User = Depends(require_r2_access),
    db: Session = Depends(get_db),
):
    row = db.get(R2File, file_id)
    if not row:
        raise HTTPException(status_code=404, detail="文件不存在")

    public_base = (settings.r2_public_url or "").strip()
    if not public_base:
        raise HTTPException(status_code=503, detail="R2_PUBLIC_URL 未配置")
    try:
        image_url = r2_public_url_for_key(row.key)
    except R2NotConfiguredError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc

    team_id = None
    team_name = None
    if body.target == "team":
        team_id = (body.team_id or "").strip()
        require_team_editor(db, team_id, current_user)
        team = db.get(Team, team_id)
        if not team:
            raise HTTPException(status_code=404, detail="团队不存在")
        team_name = team.name

    note_parts = []
    if row.description:
        note_parts.append(row.description)
    if row.content_type:
        note_parts.append(f"content_type={row.content_type}")
    note_parts.append(f"r2_key={row.key}")
    note = "\n".join(note_parts)[:2000]

    asset = UserAsset(
        id=new_asset_id(),
        user_id=current_user.id,
        team_id=team_id,
        name=(row.filename or "file")[:128],
        kind="other",
        image_url=image_url,
        note=note or None,
    )
    db.add(asset)
    db.commit()
    db.refresh(asset)
    ticket = issue_media_ticket(current_user.id)["media_ticket"]
    return AssetOut(
        id=asset.id,
        name=asset.name,
        kind=asset.kind,
        image_url=append_media_ticket(asset.image_url, ticket)
        if asset.image_url.startswith("/api/")
        else asset.image_url,
        note=asset.note,
        source_canvas_id=asset.source_canvas_id,
        source_canvas_name=asset.source_canvas_name,
        source_node_id=asset.source_node_id,
        team_id=asset.team_id,
        team_name=team_name,
        owner_id=current_user.id,
        owner_name=current_user.username,
        created_at=asset.created_at,
        updated_at=asset.updated_at,
    )
