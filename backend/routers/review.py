"""Video review: JWT publish APIs + anonymous public APIs."""

from __future__ import annotations

import tempfile
from pathlib import Path
from urllib.parse import parse_qs, urlparse

import httpx
from fastapi import APIRouter, Depends, File, HTTPException, UploadFile
from sqlalchemy import case, func, or_
from sqlalchemy.orm import Session

from core.comfyui_settings import comfyui_nodes_list, resolve_comfyui_node_url
from core.config import settings
from core.dependencies import get_current_user
from db.session import get_db
from models import User
from models.review_video import ReviewComment, ReviewVideo, utcnow
from schemas.review import (
    ReviewCommentCreate,
    ReviewCommentOut,
    ReviewImportVideoRequest,
    ReviewImportVideoResponse,
    ReviewPresignVideoRequest,
    ReviewPresignVideoResponse,
    ReviewVideoCreate,
    ReviewVideoDetailOut,
    ReviewVideoOut,
    ReviewVideoUploadResponse,
)
from services.media_access import (
    sanitize_filename,
    sanitize_upload_rel_path,
    user_can_access_comfy_output,
    user_can_access_upload,
)
from services.r2 import (
    R2NotConfiguredError,
    delete_file,
    ensure_encoded_r2_public_url,
    generate_presigned_upload_url,
    is_r2_configured,
    is_r2_public_asset_url,
    key_from_r2_public_url,
    r2_public_url_for_key,
    upload_fileobj,
)

router = APIRouter(prefix="/api/review", tags=["review"])

PRESIGN_EXPIRES = 3600
MAX_UPLOAD_BYTES = 2 * 1024 * 1024 * 1024  # 2 GiB (nginx + server proxy)
MAX_THUMB_BYTES = 10 * 1024 * 1024
_VIDEO_TYPES = {
    "video/mp4",
    "video/webm",
    "video/quicktime",
    "video/x-msvideo",
    "video/x-matroska",
    "application/octet-stream",
}
_IMAGE_TYPES = {
    "image/jpeg",
    "image/png",
    "image/webp",
    "image/gif",
}


def _looks_like_video(filename: str, content_type: str) -> bool:
    ctype = (content_type or "").strip().lower()
    name = (filename or "").lower()
    return ctype.startswith("video/") or name.endswith(
        (".mp4", ".webm", ".mov", ".mkv", ".avi", ".m4v")
    ) or ctype in _VIDEO_TYPES


_UPLOAD_ROOT = Path("uploads")


def _parse_studio_media_url(source_url: str) -> dict | None:
    """Detect /api/view or /api/uploads media; return {kind, ...} or None."""
    raw = (source_url or "").strip()
    if not raw:
        return None
    if raw.startswith("/"):
        parsed = urlparse(raw)
    else:
        parsed = urlparse(raw)
        # Absolute URL to our own API paths
        path = parsed.path or ""
        if not (path.startswith("/api/view") or path.startswith("/api/uploads/")):
            return None
    path = parsed.path or ""
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


def _upload_path_to_r2(file_path: Path, filename: str, content_type: str) -> dict:
    size = int(file_path.stat().st_size)
    if size > MAX_UPLOAD_BYTES:
        raise HTTPException(
            status_code=413,
            detail=f"视频过大，最大允许 {MAX_UPLOAD_BYTES // (1024 * 1024)} MB",
        )
    with file_path.open("rb") as fh:
        result = upload_fileobj(fh, filename, content_type, prefix="review")
    return {**result, "filename": filename, "size_bytes": size}


def _public_media_url(url: str | None) -> str | None:
    """Only return URLs that anonymous clients can load."""
    if not url:
        return None
    raw = url.strip()
    if not raw:
        return None
    encoded = ensure_encoded_r2_public_url(raw) or raw
    if is_r2_public_asset_url(encoded):
        return encoded
    lower = encoded.lower()
    if "/api/uploads" in lower or "/api/view" in lower:
        return None
    if encoded.startswith("http://") or encoded.startswith("https://"):
        return encoded
    return None


def _rehost_local_upload_image(db: Session, user: User, source_url: str) -> str | None:
    """If source is /api/uploads/images/..., copy to R2 and return public URL."""
    media = _parse_studio_media_url(source_url)
    if not media or media.get("kind") != "upload":
        return None
    safe_rel = sanitize_upload_rel_path(media["rel_path"])
    if not safe_rel.startswith("images/"):
        return None
    if not user_can_access_upload(db, user, safe_rel):
        raise HTTPException(status_code=403, detail="无权访问该封面图")
    file_path = (_UPLOAD_ROOT / safe_rel).resolve()
    root = _UPLOAD_ROOT.resolve()
    if not str(file_path).startswith(str(root)) or not file_path.is_file():
        raise HTTPException(status_code=404, detail="封面文件不存在")
    size = int(file_path.stat().st_size)
    if size > MAX_THUMB_BYTES:
        raise HTTPException(status_code=413, detail="封面过大")
    ctype = "image/png"
    name = file_path.name.lower()
    if name.endswith((".jpg", ".jpeg")):
        ctype = "image/jpeg"
    elif name.endswith(".webp"):
        ctype = "image/webp"
    elif name.endswith(".gif"):
        ctype = "image/gif"
    with file_path.open("rb") as fh:
        result = upload_fileobj(fh, file_path.name, ctype, prefix="review")
    return result["public_url"]


def _row_to_out(video: ReviewVideo, stats_row=None) -> ReviewVideoOut:
    avg = None
    likes = dislikes = comments = 0
    if stats_row is not None:
        avg = float(stats_row.avg_rating) if stats_row.avg_rating is not None else None
        likes = int(stats_row.like_count or 0)
        dislikes = int(stats_row.dislike_count or 0)
        comments = int(stats_row.comment_count or 0)
    return ReviewVideoOut(
        id=video.id,
        title=video.title,
        description=video.description,
        video_url=_public_media_url(video.video_url) or video.video_url,
        thumbnail_url=_public_media_url(video.thumbnail_url),
        publisher_id=video.publisher_id,
        publisher_name=video.publisher_name,
        published_at=video.published_at,
        is_active=video.is_active,
        avg_rating=round(avg, 2) if avg is not None else None,
        like_count=likes,
        dislike_count=dislikes,
        comment_count=comments,
    )


def _stats_map(db: Session, video_ids: list[int]) -> dict:
    if not video_ids:
        return {}
    rows = (
        db.query(
            ReviewComment.video_id,
            func.avg(ReviewComment.rating).label("avg_rating"),
            func.sum(case((ReviewComment.liked.is_(True), 1), else_=0)).label(
                "like_count"
            ),
            func.sum(case((ReviewComment.liked.is_(False), 1), else_=0)).label(
                "dislike_count"
            ),
            func.count(ReviewComment.id).label("comment_count"),
        )
        .filter(ReviewComment.video_id.in_(video_ids))
        .group_by(ReviewComment.video_id)
        .all()
    )
    return {r.video_id: r for r in rows}


@router.post("/presign-video", response_model=ReviewPresignVideoResponse)
def presign_review_video(
    body: ReviewPresignVideoRequest,
    _: User = Depends(get_current_user),
):
    """JWT-only R2 upload for review videos (does not require r2_access)."""
    if not is_r2_configured():
        raise HTTPException(status_code=503, detail="R2 未配置，无法本地上传")
    if not (settings.r2_public_url or "").strip():
        raise HTTPException(status_code=503, detail="R2_PUBLIC_URL 未配置")
    if not _looks_like_video(body.filename, body.content_type):
        raise HTTPException(status_code=400, detail="请上传视频文件")
    try:
        result = generate_presigned_upload_url(
            body.filename,
            body.content_type or "video/mp4",
            expires=PRESIGN_EXPIRES,
            prefix="review",
        )
        public_url = r2_public_url_for_key(result["key"])
    except R2NotConfiguredError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    except RuntimeError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc
    return ReviewPresignVideoResponse(
        upload_url=result["url"],
        key=result["key"],
        content_type=result["content_type"],
        public_url=public_url,
        expires_in=PRESIGN_EXPIRES,
    )


@router.post("/upload-video", response_model=ReviewVideoUploadResponse)
async def upload_review_video(
    file: UploadFile = File(...),
    _: User = Depends(get_current_user),
):
    """Same-origin multipart upload → R2 (avoids browser CORS to R2)."""
    if not is_r2_configured():
        raise HTTPException(status_code=503, detail="R2 未配置，无法本地上传")
    if not (settings.r2_public_url or "").strip():
        raise HTTPException(status_code=503, detail="R2_PUBLIC_URL 未配置")
    filename = file.filename or "video.mp4"
    content_type = file.content_type or "video/mp4"
    if not _looks_like_video(filename, content_type):
        raise HTTPException(status_code=400, detail="请上传视频文件")
    # SpooledTemporaryFile may not expose size until read; enforce via Content-Length if present
    try:
        file.file.seek(0, 2)
        size = int(file.file.tell() or 0)
        file.file.seek(0)
    except Exception:
        size = 0
    if size > MAX_UPLOAD_BYTES:
        raise HTTPException(
            status_code=413,
            detail=f"视频过大，最大允许 {MAX_UPLOAD_BYTES // (1024 * 1024)} MB",
        )
    try:
        result = upload_fileobj(
            file.file,
            filename,
            content_type,
            prefix="review",
        )
    except R2NotConfiguredError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    except RuntimeError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc
    return ReviewVideoUploadResponse(
        key=result["key"],
        content_type=result["content_type"],
        public_url=result["public_url"],
        filename=filename,
        size_bytes=size,
    )


@router.post("/upload-thumbnail", response_model=ReviewVideoUploadResponse)
async def upload_review_thumbnail(
    file: UploadFile = File(...),
    _: User = Depends(get_current_user),
):
    """Upload cover image to R2 (public) for anonymous review pages."""
    if not is_r2_configured():
        raise HTTPException(status_code=503, detail="R2 未配置，无法上传封面")
    if not (settings.r2_public_url or "").strip():
        raise HTTPException(status_code=503, detail="R2_PUBLIC_URL 未配置")
    filename = file.filename or "cover.jpg"
    content_type = (file.content_type or "image/jpeg").strip().lower()
    if content_type not in _IMAGE_TYPES and not filename.lower().endswith(
        (".jpg", ".jpeg", ".png", ".webp", ".gif")
    ):
        raise HTTPException(status_code=400, detail="请上传 JPG / PNG / WebP / GIF 封面")
    try:
        file.file.seek(0, 2)
        size = int(file.file.tell() or 0)
        file.file.seek(0)
    except Exception:
        size = 0
    if size > MAX_THUMB_BYTES:
        raise HTTPException(status_code=413, detail="封面过大，最大 10 MB")
    if content_type not in _IMAGE_TYPES:
        content_type = "image/jpeg"
    try:
        result = upload_fileobj(
            file.file,
            filename,
            content_type,
            prefix="review",
        )
    except R2NotConfiguredError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    except RuntimeError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc
    return ReviewVideoUploadResponse(
        key=result["key"],
        content_type=result["content_type"],
        public_url=result["public_url"],
        filename=filename,
        size_bytes=size,
    )


@router.post("/import-video", response_model=ReviewImportVideoResponse)
async def import_review_video(
    body: ReviewImportVideoRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Rehost private studio media (/api/view|/api/uploads) to R2 for anonymous review."""
    raw = (body.source_url or "").strip()
    if not raw:
        raise HTTPException(status_code=400, detail="缺少 source_url")

    if is_r2_public_asset_url(raw):
        key = key_from_r2_public_url(raw)
        return ReviewImportVideoResponse(
            public_url=raw,
            key=key,
            filename=Path(key or "video.mp4").name,
            rehosted=False,
        )

    media = _parse_studio_media_url(raw)
    if media is None:
        # Already a public external URL — no rehost
        if raw.startswith("http://") or raw.startswith("https://"):
            return ReviewImportVideoResponse(
                public_url=raw,
                filename="video.mp4",
                rehosted=False,
            )
        raise HTTPException(status_code=400, detail="无法识别的视频地址")

    if not is_r2_configured() or not (settings.r2_public_url or "").strip():
        raise HTTPException(status_code=503, detail="R2 未配置，无法转存生成历史视频")

    try:
        if media["kind"] == "upload":
            safe_rel = sanitize_upload_rel_path(media["rel_path"])
            if not user_can_access_upload(db, current_user, safe_rel):
                raise HTTPException(status_code=403, detail="无权访问该视频")
            file_path = (_UPLOAD_ROOT / safe_rel).resolve()
            root = _UPLOAD_ROOT.resolve()
            if not str(file_path).startswith(str(root)) or not file_path.is_file():
                raise HTTPException(status_code=404, detail="视频文件不存在")
            filename = file_path.name
            ctype = "video/mp4"
            if filename.lower().endswith(".webm"):
                ctype = "video/webm"
            result = _upload_path_to_r2(file_path, filename, ctype)
            return ReviewImportVideoResponse(
                public_url=result["public_url"],
                key=result["key"],
                content_type=result["content_type"],
                filename=result["filename"],
                size_bytes=result["size_bytes"],
                rehosted=True,
            )

        # ComfyUI /api/view proxy → temp file → R2
        safe_name = sanitize_filename(media["filename"])
        safe_subfolder = (media.get("subfolder") or "").strip().replace("\\", "/").strip("/")
        if safe_subfolder and not all(
            part and part not in (".", "..") for part in safe_subfolder.split("/")
        ):
            raise HTTPException(status_code=400, detail="非法 subfolder")
        if not user_can_access_comfy_output(
            db, current_user, safe_name, subfolder=safe_subfolder
        ):
            raise HTTPException(status_code=403, detail="无权访问该视频")

        params = {"filename": safe_name, "type": media.get("type") or "output"}
        if safe_subfolder:
            params["subfolder"] = safe_subfolder
        from urllib.parse import parse_qs, urlparse

        node_hint = None
        parsed_src = urlparse(raw or "")
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
            ctype = "video/webm" if suffix.lower() == ".webm" else "video/mp4"
            result = _upload_path_to_r2(tmp_path, safe_name, ctype)
            return ReviewImportVideoResponse(
                public_url=result["public_url"],
                key=result["key"],
                content_type=result["content_type"],
                filename=result["filename"],
                size_bytes=result["size_bytes"],
                rehosted=True,
            )
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


@router.post("/videos", response_model=ReviewVideoOut)
def publish_video(
    body: ReviewVideoCreate,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    publisher_name = (
        (current_user.display_name or "").strip() or current_user.username
    )[:64]
    video_url = ensure_encoded_r2_public_url(body.video_url.strip()) or body.video_url.strip()
    thumb_raw = (body.thumbnail_url or "").strip() or None
    thumbnail_url = None
    if thumb_raw:
        thumbnail_url = _public_media_url(thumb_raw)
        if not thumbnail_url:
            # Private studio upload → rehost to R2 for anonymous review pages
            try:
                thumbnail_url = _rehost_local_upload_image(db, current_user, thumb_raw)
            except HTTPException:
                raise
            except Exception as exc:
                raise HTTPException(
                    status_code=502, detail=f"封面转存失败: {exc}"
                ) from exc
            if not thumbnail_url:
                raise HTTPException(
                    status_code=400,
                    detail="封面必须是公开可访问的图片，请重新上传封面",
                )
    row = ReviewVideo(
        title=body.title.strip(),
        description=(body.description or "").strip() or None,
        video_url=video_url,
        thumbnail_url=thumbnail_url,
        publisher_id=current_user.id,
        publisher_name=publisher_name,
        published_at=utcnow(),
        is_active=True,
    )
    db.add(row)
    db.commit()
    db.refresh(row)
    return _row_to_out(row)


@router.get("/videos/mine", response_model=list[ReviewVideoOut])
def list_my_videos(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    rows = (
        db.query(ReviewVideo)
        .filter(ReviewVideo.publisher_id == current_user.id)
        .order_by(ReviewVideo.published_at.desc())
        .all()
    )
    smap = _stats_map(db, [r.id for r in rows])
    return [_row_to_out(r, smap.get(r.id)) for r in rows]


@router.delete("/videos/{video_id}")
def unpublish_video(
    video_id: int,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    row = db.get(ReviewVideo, video_id)
    if not row:
        raise HTTPException(status_code=404, detail="视频不存在")
    if row.publisher_id != current_user.id and current_user.role != "admin":
        raise HTTPException(status_code=403, detail="无权撤回该视频")

    video_url = (row.video_url or "").strip()
    thumb_url = (row.thumbnail_url or "").strip()
    row.is_active = False
    db.commit()

    r2_deleted: list[str] = []
    r2_skipped: list[str] = []
    if is_r2_configured():
        for url in (video_url, thumb_url):
            if not url:
                continue
            key = key_from_r2_public_url(url)
            # Only auto-delete objects we uploaded under review/
            if not key or not key.startswith("review/"):
                continue
            still_used = (
                db.query(ReviewVideo.id)
                .filter(
                    ReviewVideo.is_active.is_(True),
                    or_(
                        ReviewVideo.video_url == url,
                        ReviewVideo.thumbnail_url == url,
                    ),
                )
                .first()
            )
            if still_used:
                r2_skipped.append(key)
                continue
            try:
                delete_file(key)
                r2_deleted.append(key)
            except Exception:
                # Unpublish already succeeded; R2 cleanup is best-effort
                r2_skipped.append(key)

    return {
        "ok": True,
        "id": video_id,
        "is_active": False,
        "r2_deleted": r2_deleted,
        "r2_skipped": r2_skipped,
    }


@router.get("/public/videos", response_model=list[ReviewVideoOut])
def list_public_videos(db: Session = Depends(get_db)):
    rows = (
        db.query(ReviewVideo)
        .filter(ReviewVideo.is_active.is_(True))
        .order_by(ReviewVideo.published_at.desc())
        .all()
    )
    smap = _stats_map(db, [r.id for r in rows])
    return [_row_to_out(r, smap.get(r.id)) for r in rows]


@router.get("/public/videos/{video_id}", response_model=ReviewVideoDetailOut)
def get_public_video(video_id: int, db: Session = Depends(get_db)):
    row = db.get(ReviewVideo, video_id)
    if not row or not row.is_active:
        raise HTTPException(status_code=404, detail="视频不存在或已下架")
    smap = _stats_map(db, [row.id])
    base = _row_to_out(row, smap.get(row.id))
    comments = (
        db.query(ReviewComment)
        .filter(ReviewComment.video_id == video_id)
        .order_by(ReviewComment.created_at.desc())
        .all()
    )
    return ReviewVideoDetailOut(
        **base.model_dump(),
        comments=[ReviewCommentOut.model_validate(c) for c in comments],
    )


@router.post(
    "/public/videos/{video_id}/comment",
    response_model=ReviewCommentOut,
)
def post_public_comment(
    video_id: int,
    body: ReviewCommentCreate,
    db: Session = Depends(get_db),
):
    row = db.get(ReviewVideo, video_id)
    if not row or not row.is_active:
        raise HTTPException(status_code=404, detail="视频不存在或已下架")
    comment = ReviewComment(
        video_id=video_id,
        reviewer_name=body.reviewer_name.strip()[:64],
        rating=int(body.rating),
        liked=body.liked,
        comment=(body.comment or "").strip() or None,
        created_at=utcnow(),
    )
    db.add(comment)
    db.commit()
    db.refresh(comment)
    return ReviewCommentOut.model_validate(comment)
