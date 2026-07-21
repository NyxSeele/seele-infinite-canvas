"""Video review: JWT publish APIs + anonymous public APIs."""

from __future__ import annotations

from pathlib import Path

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile
from sqlalchemy import case, func, or_
from sqlalchemy.orm import Session

from core.comfyui_settings import comfyui_nodes_list
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
    sanitize_upload_rel_path,
    user_can_access_upload,
)
from services.studio_media_rehost import parse_studio_media_url, rehost_studio_video
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
    media = parse_studio_media_url(source_url)
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
    result = await rehost_studio_video(
        db,
        current_user,
        body.source_url,
        prefix="review",
        allow_external_pass_through=True,
    )
    return ReviewImportVideoResponse(
        public_url=result["public_url"],
        key=result.get("key"),
        content_type=result.get("content_type") or "video/mp4",
        filename=result.get("filename") or "video.mp4",
        size_bytes=int(result.get("size_bytes") or 0),
        rehosted=bool(result.get("rehosted")),
    )


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
