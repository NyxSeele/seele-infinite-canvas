"""上传文件内容校验（magic bytes），不信任客户端 Content-Type。"""

from __future__ import annotations

import io
from math import gcd

from fastapi import HTTPException

ALLOWED_IMAGE_MIMES = frozenset({"image/jpeg", "image/png", "image/webp", "image/gif"})
MAX_IMAGE_BYTES = 10 * 1024 * 1024
UPLOAD_MAX_EDGE = 1280
_HEIC_BRANDS = frozenset({b"heic", b"heix", b"hevc", b"heif", b"mif1", b"msf1"})


def _detect_image_mime(content: bytes) -> str | None:
    if len(content) < 12:
        return None
    if content[:3] == b"\xff\xd8\xff":
        return "image/jpeg"
    if content[:8] == b"\x89PNG\r\n\x1a\n":
        return "image/png"
    if content[:6] in (b"GIF87a", b"GIF89a"):
        return "image/gif"
    if content[:4] == b"RIFF" and content[8:12] == b"WEBP":
        return "image/webp"
    if content[4:8] == b"ftyp":
        brand = content[8:12]
        if brand in _HEIC_BRANDS:
            return "image/heic"
    return None


def _convert_heic_to_jpeg(content: bytes, *, max_edge: int = UPLOAD_MAX_EDGE) -> bytes:
    try:
        from pillow_heif import register_heif_opener
        from PIL import Image

        register_heif_opener()
        img = Image.open(io.BytesIO(content))
        w, h = img.size
        max_dim = max(w, h)
        if max_dim > max_edge:
            scale = max_edge / max_dim
            img = img.resize(
                (max(1, int(w * scale)), max(1, int(h * scale))),
                Image.Resampling.LANCZOS,
            )
        out = io.BytesIO()
        img.convert("RGB").save(out, format="JPEG", quality=82, optimize=True)
        return out.getvalue()
    except Exception as exc:
        raise HTTPException(
            status_code=400,
            detail="无法处理 HEIC/HEIF 图片，请在相册中选择「兼容性最佳」或导出为 JPG/PNG 后上传",
        ) from exc


def aspect_ratio_string(width: int, height: int) -> str:
    w = max(1, int(width))
    h = max(1, int(height))
    g = gcd(w, h)
    return f"{w // g}:{h // g}"


def image_dimensions(content: bytes) -> tuple[int, int]:
    from PIL import Image

    with Image.open(io.BytesIO(content)) as img:
        w, h = img.size
    return int(w), int(h)


def normalize_image_upload(content: bytes, declared_mime: str | None = None) -> tuple[bytes, str]:
    """校验并按需将 HEIC 转为 JPEG；移动端空 Content-Type 依赖 magic bytes。"""
    detected = _detect_image_mime(content)
    if detected == "image/heic":
        content = _convert_heic_to_jpeg(content)
    mime = validate_image_upload(content, declared_mime)
    return content, mime


def validate_image_upload(content: bytes, declared_mime: str | None = None) -> str:
    if len(content) > MAX_IMAGE_BYTES:
        raise HTTPException(status_code=400, detail="图片大小不能超过 10MB")
    detected = _detect_image_mime(content)
    if not detected:
        raise HTTPException(status_code=400, detail="无法识别的图片格式")
    declared = (declared_mime or "").split(";", 1)[0].strip().lower()
    if declared and declared in ALLOWED_IMAGE_MIMES and declared != detected:
        # 声明与内容不一致时以 magic bytes 为准（webp/gif 等浏览器偶发误报）
        if declared not in ("image/jpeg", "image/png"):
            pass
    if detected not in ALLOWED_IMAGE_MIMES:
        raise HTTPException(status_code=400, detail="不支持的图片格式")
    return detected


def suffix_for_mime(mime: str, fallback: str = ".jpg") -> str:
    return {
        "image/jpeg": ".jpg",
        "image/png": ".png",
        "image/webp": ".webp",
        "image/gif": ".gif",
    }.get(mime, fallback)


ALLOWED_VIDEO_MIMES = frozenset({"video/mp4", "video/quicktime"})
MAX_STYLE_VIDEO_BYTES = 100 * 1024 * 1024
MAX_STYLE_VIDEO_SECONDS = 60


def _detect_video_mime(content: bytes) -> str | None:
    if len(content) < 12:
        return None
    # ISO BMFF (mp4/mov)
    if len(content) >= 8 and content[4:8] == b"ftyp":
        brand = content[8:12]
        if brand in (b"qt  ", b"moov", b"isom", b"mp42", b"avc1", b"M4V "):
            return "video/quicktime" if brand == b"qt  " else "video/mp4"
        return "video/mp4"
    return None


def validate_style_video_upload(content: bytes, declared_mime: str | None = None) -> str:
    if len(content) > MAX_STYLE_VIDEO_BYTES:
        raise HTTPException(status_code=400, detail="视频大小不能超过 100MB")
    detected = _detect_video_mime(content)
    if not detected:
        raise HTTPException(status_code=400, detail="无法识别的视频格式，仅支持 MP4 / MOV")
    declared = (declared_mime or "").split(";", 1)[0].strip().lower()
    if declared and declared in ALLOWED_VIDEO_MIMES and declared != detected:
        pass
    if detected not in ALLOWED_VIDEO_MIMES:
        raise HTTPException(status_code=400, detail="不支持的视频格式，仅允许 MP4 / MOV")
    return detected


def video_suffix_for_mime(mime: str) -> str:
    return ".mov" if mime == "video/quicktime" else ".mp4"
