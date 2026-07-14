from pathlib import Path
from uuid import uuid4

from botocore.exceptions import BotoCoreError, ClientError
from fastapi import APIRouter, Depends, File, HTTPException, UploadFile
from sqlalchemy.orm import Session

from core.dependencies import get_current_user
from db.session import get_db
from models import User
from models.user_upload import UserUpload
from schemas.upload import (
    CanvasImagePresignRequest,
    CanvasImagePresignResponse,
    CanvasImageRegisterRequest,
    CanvasImageRegisterResponse,
    UploadCapabilitiesResponse,
)
from services.media_access import append_media_ticket, issue_media_ticket
from services.r2 import (
    R2NotConfiguredError,
    _client,
    generate_presigned_upload_url,
    is_r2_configured,
    r2_public_url_for_key,
)
from services.upload_validation import (
    aspect_ratio_string,
    image_dimensions,
    normalize_image_upload,
    suffix_for_mime,
)

router = APIRouter(prefix="/api/upload", tags=["upload"])

UPLOAD_DIR = Path("uploads/images")
UPLOAD_DIR.mkdir(parents=True, exist_ok=True)

CANVAS_KEY_PREFIX = "canvas/"
CANVAS_R2_MAX_BYTES = 20 * 1024 * 1024
CANVAS_PRESIGN_EXPIRES = 3600
_CANVAS_IMAGE_CT = frozenset({"image/jpeg", "image/png", "image/webp", "image/gif"})
_HEIC_EXTS = frozenset({".heic", ".heif"})
_CANVAS_IMAGE_EXTS = frozenset({".jpg", ".jpeg", ".png", ".webp", ".gif"})


def _ensure_canvas_r2() -> None:
    if not is_r2_configured():
        raise HTTPException(status_code=503, detail="R2 未配置")


def _validate_canvas_image_meta(filename: str, content_type: str, size_bytes: int) -> str:
    if size_bytes > CANVAS_R2_MAX_BYTES:
        raise HTTPException(
            status_code=413,
            detail=f"图片大小不能超过 {CANVAS_R2_MAX_BYTES // (1024 * 1024)}MB",
        )
    ext = Path(filename or "image.jpg").suffix.lower()
    if ext in _HEIC_EXTS:
        raise HTTPException(
            status_code=400,
            detail="HEIC/HEIF 请使用标准上传接口（服务端会自动转换）",
        )
    ctype = (content_type or "").split(";", 1)[0].strip().lower()
    if "heic" in ctype or "heif" in ctype:
        raise HTTPException(
            status_code=400,
            detail="HEIC/HEIF 请使用标准上传接口（服务端会自动转换）",
        )
    if ctype in _CANVAS_IMAGE_CT:
        return ctype
    if ext in _CANVAS_IMAGE_EXTS:
        return {
            ".jpg": "image/jpeg",
            ".jpeg": "image/jpeg",
            ".png": "image/png",
            ".webp": "image/webp",
            ".gif": "image/gif",
        }[ext]
    raise HTTPException(status_code=400, detail="不支持的图片格式")


def _assert_canvas_key(key: str) -> str:
    normalized = (key or "").strip().lstrip("/")
    if not normalized.startswith(CANVAS_KEY_PREFIX):
        raise HTTPException(status_code=400, detail="无效的上传 key")
    return normalized


def _head_canvas_object(key: str) -> int:
    from core.config import settings

    try:
        head = _client().head_object(
            Bucket=settings.r2_bucket_name.strip(),
            Key=key,
        )
    except (BotoCoreError, ClientError) as exc:
        raise HTTPException(
            status_code=400,
            detail="R2 上未找到该文件，请确认直传已完成",
        ) from exc
    return int(head.get("ContentLength") or 0)


_MAX_DIM_EDGE = 8192
_HEADER_RANGE_BYTES = 65535


def _validate_client_dimensions(
    width: int | None,
    height: int | None,
    *,
    object_size: int,
) -> tuple[int, int] | None:
    if width is None or height is None:
        return None
    if width < 1 or height < 1 or width > _MAX_DIM_EDGE or height > _MAX_DIM_EDGE:
        return None
    pixels = width * height
    if pixels < 64 or pixels > _MAX_DIM_EDGE * _MAX_DIM_EDGE:
        return None
    # 粗略校验：每像素至少 0.25 字节（JPEG 压缩后），避免明显造假
    if object_size > 0 and object_size < pixels * 0.25:
        return None
    return width, height


def _read_r2_object_bytes(key: str, *, range_header: str | None = None) -> bytes:
    from core.config import settings

    kwargs: dict = {
        "Bucket": settings.r2_bucket_name.strip(),
        "Key": key,
    }
    if range_header:
        kwargs["Range"] = range_header
    try:
        resp = _client().get_object(**kwargs)
        return resp["Body"].read()
    except (BotoCoreError, ClientError) as exc:
        raise HTTPException(
            status_code=400,
            detail="无法读取 R2 图片以计算尺寸",
        ) from exc


def _dimensions_from_r2_object(key: str) -> tuple[int, int]:
    try:
        header = _read_r2_object_bytes(key, range_header=f"bytes=0-{_HEADER_RANGE_BYTES}")
        if header:
            return image_dimensions(header)
    except HTTPException:
        raise
    except Exception:
        pass

    content = _read_r2_object_bytes(key)
    if len(content) > CANVAS_R2_MAX_BYTES:
        raise HTTPException(status_code=413, detail="图片大小超出限制")
    try:
        return image_dimensions(content)
    except Exception as exc:
        raise HTTPException(
            status_code=400,
            detail="无法解析图片尺寸",
        ) from exc


@router.get("/capabilities", response_model=UploadCapabilitiesResponse)
async def upload_capabilities(
    _: User = Depends(get_current_user),
):
    return UploadCapabilitiesResponse(
        r2_direct=is_r2_configured(),
        max_size_bytes=CANVAS_R2_MAX_BYTES,
    )


@router.post("/presign-image", response_model=CanvasImagePresignResponse)
async def presign_canvas_image(
    body: CanvasImagePresignRequest,
    current_user: User = Depends(get_current_user),
):
    _ = current_user
    _ensure_canvas_r2()
    content_type = _validate_canvas_image_meta(
        body.filename, body.content_type, body.size_bytes
    )
    try:
        result = generate_presigned_upload_url(
            body.filename,
            content_type,
            expires=CANVAS_PRESIGN_EXPIRES,
            prefix=CANVAS_KEY_PREFIX.rstrip("/"),
        )
    except R2NotConfiguredError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    except RuntimeError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc
    return CanvasImagePresignResponse(
        upload_url=result["url"],
        key=result["key"],
        content_type=result["content_type"],
        expires_in=CANVAS_PRESIGN_EXPIRES,
    )


@router.post("/register-image", response_model=CanvasImageRegisterResponse)
async def register_canvas_image(
    body: CanvasImageRegisterRequest,
    current_user: User = Depends(get_current_user),
):
    _ = current_user
    _ensure_canvas_r2()
    key = _assert_canvas_key(body.key)
    size = _head_canvas_object(key)
    if size > CANVAS_R2_MAX_BYTES:
        raise HTTPException(status_code=413, detail="图片大小超出限制")
    _validate_canvas_image_meta(
        body.filename or key.rsplit("/", 1)[-1],
        body.content_type,
        size,
    )
    dims = _validate_client_dimensions(body.width, body.height, object_size=size)
    if dims:
        width, height = dims
    else:
        width, height = _dimensions_from_r2_object(key)
    try:
        public_url = r2_public_url_for_key(key)
    except R2NotConfiguredError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    return CanvasImageRegisterResponse(
        url=public_url,
        key=key,
        width=width,
        height=height,
        aspect_ratio=aspect_ratio_string(width, height),
    )


@router.post("/image")
async def upload_image(
    file: UploadFile = File(...),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    content = await file.read()
    size_mb = len(content) / (1024 * 1024)
    if size_mb > 10:
        raise HTTPException(status_code=413, detail="图片大小不能超过 10MB")
    content, mime = normalize_image_upload(content, file.content_type)

    suffix = suffix_for_mime(mime, Path(file.filename or "image.jpg").suffix or ".jpg")
    if suffix.lower() not in (".jpg", ".jpeg", ".png", ".webp", ".gif"):
        suffix = ".jpg"
    filename = f"{uuid4()}{suffix}"
    save_path = UPLOAD_DIR / filename

    with open(save_path, "wb") as f:
        f.write(content)

    width, height = image_dimensions(content)
    rel_path = f"images/{filename}"
    db.add(UserUpload(user_id=current_user.id, path=rel_path))
    db.commit()

    ticket = issue_media_ticket(current_user.id)["media_ticket"]
    path = append_media_ticket(f"/api/uploads/{rel_path}", ticket)
    return {
        "url": path,
        "filename": filename,
        "media_ticket": ticket,
        "width": width,
        "height": height,
        "aspect_ratio": aspect_ratio_string(width, height),
    }
