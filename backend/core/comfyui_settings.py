"""ComfyUI 内网地址配置（SaaS 部署时仅 backend 可访问，不暴露公网）。"""

from urllib.parse import urlparse, urlunparse

from core.config import settings


def comfyui_http_url() -> str:
    return (settings.comfyui_url or "http://127.0.0.1:8000").rstrip("/")


def comfyui_ws_url() -> str:
    explicit = (settings.comfyui_ws_url or "").strip()
    if explicit:
        return explicit.rstrip("/")
    parsed = urlparse(comfyui_http_url())
    scheme = "wss" if parsed.scheme == "https" else "ws"
    netloc = parsed.netloc or "127.0.0.1:8000"
    return urlunparse((scheme, netloc, "/ws", "", "", ""))


def comfyui_checkpoints_url() -> str:
    return f"{comfyui_http_url()}/models/checkpoints"
