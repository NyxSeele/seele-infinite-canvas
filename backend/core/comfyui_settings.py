"""ComfyUI 内网地址配置（SaaS 部署时仅 backend 可访问，不暴露公网）。"""

from urllib.parse import urlparse, urlunparse

from core.config import settings


def comfyui_nodes_list() -> list[str]:
    raw = (settings.comfyui_nodes or "").strip()
    if raw:
        return [u.strip().rstrip("/") for u in raw.split(",") if u.strip()]
    return [(settings.comfyui_url or "http://127.0.0.1:8000").rstrip("/")]


def comfyui_http_url() -> str:
    nodes = comfyui_nodes_list()
    return nodes[0] if nodes else "http://127.0.0.1:8000"


def comfyui_node_port(node_url: str | None) -> str | None:
    """从 ComfyUI HTTP URL 提取端口，供 /api/view?node= 使用。"""
    if not node_url:
        return None
    parsed = urlparse(node_url.strip())
    if parsed.port:
        return str(parsed.port)
    if parsed.scheme == "https":
        return "443"
    if parsed.scheme == "http":
        return "80"
    return None


def resolve_comfyui_node_url(node: str | None = None) -> str:
    """
    解析 ComfyUI 节点 HTTP 基址。
    node 可为：空（首节点）、端口号（8001）、完整 http(s) URL。
    """
    raw = (node or "").strip()
    if not raw:
        return comfyui_http_url()
    if raw.startswith("http://") or raw.startswith("https://"):
        return raw.rstrip("/")
    nodes = comfyui_nodes_list()
    for url in nodes:
        port = comfyui_node_port(url)
        if port == raw or url.endswith(f":{raw}"):
            return url
    return comfyui_http_url()


def comfyui_ws_url_for_node(node_url: str | None = None) -> str:
    """按目标 ComfyUI HTTP 基址生成 WebSocket URL。"""
    explicit = (settings.comfyui_ws_url or "").strip()
    base = resolve_comfyui_node_url(node_url)
    if explicit and not node_url:
        return explicit.rstrip("/")
    parsed = urlparse(base)
    scheme = "wss" if parsed.scheme == "https" else "ws"
    netloc = parsed.netloc or "127.0.0.1:8000"
    return urlunparse((scheme, netloc, "/ws", "", "", ""))


def comfyui_ws_url() -> str:
    return comfyui_ws_url_for_node(None)


def comfyui_checkpoints_url() -> str:
    return f"{comfyui_http_url()}/models/checkpoints"
