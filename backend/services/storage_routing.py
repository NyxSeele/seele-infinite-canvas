"""Storage backend routing: local disk + AutoDL public vs R2."""

from __future__ import annotations

from typing import Literal

from core.config import settings
from services.r2 import is_r2_configured

Feature = Literal["canvas", "team", "review"]
Backend = Literal["local", "r2"]

CANVAS_LOCAL_MAX_BYTES = 20 * 1024 * 1024
TEAM_LOCAL_MAX_BYTES = 2 * 1024 * 1024 * 1024


def media_public_base() -> str | None:
    raw = (settings.media_public_base or "").strip().rstrip("/")
    return raw or None


def resolve_backend(feature: Feature) -> Backend:
    if feature == "review":
        return "r2"
    raw = {
        "canvas": (settings.storage_canvas or "auto").strip().lower(),
        "team": (settings.storage_team or "auto").strip().lower(),
    }[feature]
    if raw == "auto":
        if media_public_base():
            return "local"
        return "r2" if is_r2_configured() else "local"
    if raw == "local":
        return "local"
    return "r2"


def build_media_public_url(path: str) -> str:
    normalized = path if path.startswith("/") else f"/{path}"
    base = media_public_base()
    if base:
        return f"{base}{normalized}"
    return normalized


def max_bytes_for(feature: Feature) -> int:
    if feature == "canvas":
        return CANVAS_LOCAL_MAX_BYTES
    if feature == "team":
        return TEAM_LOCAL_MAX_BYTES
    return CANVAS_LOCAL_MAX_BYTES


def upload_capabilities_payload() -> dict:
    r2_public_url: str | None = None
    if is_r2_configured():
        try:
            r2_public_url = (settings.r2_public_url or "").strip().rstrip("/") or None
        except Exception:
            r2_public_url = None

    canvas_backend = resolve_backend("canvas")
    team_backend = resolve_backend("team")
    review_backend = resolve_backend("review")

    return {
        "media_public_base": media_public_base(),
        "canvas": {
            "backend": canvas_backend,
            "max_size_bytes": CANVAS_LOCAL_MAX_BYTES,
        },
        "team": {
            "backend": team_backend,
            "max_size_bytes": TEAM_LOCAL_MAX_BYTES,
        },
        "review": {
            "backend": review_backend,
            "r2_public_url": r2_public_url,
        },
        "r2_direct": is_r2_configured(),
        "max_size_bytes": CANVAS_LOCAL_MAX_BYTES,
        "r2_public_url": r2_public_url,
    }
