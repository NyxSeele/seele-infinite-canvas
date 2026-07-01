"""上传文件内容校验（magic bytes），不信任客户端 Content-Type。"""

from __future__ import annotations

from fastapi import HTTPException

ALLOWED_IMAGE_MIMES = frozenset({"image/jpeg", "image/png", "image/webp", "image/gif"})
MAX_IMAGE_BYTES = 10 * 1024 * 1024


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
    return None


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
