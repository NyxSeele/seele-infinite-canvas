"""多 ComfyUI / GPU 节点池（单机亦可，仅解析 COMFYUI_NODES）。"""

from __future__ import annotations

import os
import threading
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from typing import Optional
from urllib.parse import urlparse

SHORT_TASK_THRESHOLD_SEC = 120
CAP_IMAGE = "image"
CAP_VIDEO = "video"
_ALL_CAPS = frozenset({CAP_IMAGE, CAP_VIDEO})


def _is_local_comfy_url(url: str) -> bool:
    host = (urlparse(url).hostname or "").lower()
    return host in ("127.0.0.1", "localhost", "::1")


def default_node_capabilities(url: str, vram_gb: int) -> frozenset[str]:
    """
    未显式标注 capability 时的默认策略：
    - 本机节点：生图 + 视频
    - 远端高显存（≥64GB，如 H800）：仅视频（无本地生图权重）
    - 其它：生图 + 视频
    """
    if _is_local_comfy_url(url):
        return _ALL_CAPS
    if int(vram_gb) >= 64:
        return frozenset({CAP_VIDEO})
    return _ALL_CAPS


def parse_capabilities_token(raw: str) -> frozenset[str]:
    parts = [p.strip().lower() for p in (raw or "").replace("+", ",").split(",") if p.strip()]
    caps = {p for p in parts if p in _ALL_CAPS}
    return frozenset(caps) if caps else _ALL_CAPS


def parse_comfyui_node_spec(
    spec: str,
    *,
    default_vram_gb: int = 32,
) -> tuple[str, int, frozenset[str]]:
    """
    解析节点规格：
    - `http://host:port`
    - `http://host:port|80`（显存 GB）
    - `http://host:port|80|video` 或 `|32|image+video`
    注意：capability 请用 `+` 连接（如 `image+video`），勿用逗号——
    `COMFYUI_NODES` 本身以逗号分隔多个节点。
    H800 示例：`https://…:8443|80|video`
    """
    raw = (spec or "").strip()
    if not raw:
        return "", int(default_vram_gb), _ALL_CAPS

    parts = [p.strip() for p in raw.split("|")]
    url = (parts[0] if parts else "").rstrip("/")
    vram = int(default_vram_gb)
    caps: frozenset[str] | None = None

    if len(parts) >= 2 and parts[1]:
        token = parts[1]
        if token.isdigit():
            vram = max(1, int(token))
        else:
            caps = parse_capabilities_token(token)
    if len(parts) >= 3 and parts[2]:
        caps = parse_capabilities_token(parts[2])

    if caps is None:
        caps = default_node_capabilities(url, vram)
    return url, vram, caps


@dataclass
class GPUNode:
    node_id: str
    comfyui_url: str  # 如 http://127.0.0.1:8000
    available_vram: int  # GB
    busy: bool = False
    current_task_id: Optional[str] = None
    estimated_free_at: Optional[datetime] = None
    capabilities: frozenset[str] = field(default_factory=lambda: _ALL_CAPS)


@dataclass
class GPUPool:
    nodes: list[GPUNode] = field(default_factory=list)
    _lock: threading.Lock = field(default_factory=threading.Lock, repr=False)
    _rr_index: int = field(default=0, repr=False)

    @classmethod
    def from_env(
        cls,
        *,
        env_var: str = "COMFYUI_NODES",
        fallback_url: str = "http://127.0.0.1:8000",
        default_vram_gb: int = 32,
    ) -> "GPUPool":
        specs: list[str] = []
        raw_env = (os.environ.get(env_var) or "").strip()
        if raw_env:
            specs = [u.strip() for u in raw_env.split(",") if u.strip()]
        else:
            try:
                from core.comfyui_settings import comfyui_nodes_list

                specs = list(comfyui_nodes_list())
            except Exception:
                specs = []

        if not specs:
            raw = (
                os.environ.get("COMFYUI_URL")
                or os.environ.get("COMFYUI_BASE")
                or fallback_url
            ).strip()
            specs = [u.strip() for u in raw.split(",") if u.strip()]
        if not specs:
            specs = [fallback_url]

        nodes: list[GPUNode] = []
        for i, spec in enumerate(specs):
            url, vram, caps = parse_comfyui_node_spec(
                spec, default_vram_gb=default_vram_gb
            )
            if not url:
                continue
            nodes.append(
                GPUNode(
                    node_id=f"gpu-{i}",
                    comfyui_url=url,
                    available_vram=vram,
                    capabilities=caps,
                )
            )
        if not nodes:
            nodes = [
                GPUNode(
                    node_id="gpu-0",
                    comfyui_url=fallback_url.rstrip("/"),
                    available_vram=default_vram_gb,
                    capabilities=default_node_capabilities(
                        fallback_url, default_vram_gb
                    ),
                )
            ]
        return cls(nodes=nodes)

    def _pick_free_node_round_robin(self, free: list[GPUNode]) -> GPUNode:
        if len(free) == 1:
            return free[0]
        start = self._rr_index % len(free)
        self._rr_index = (start + 1) % len(free)
        return free[start]

    def get_available_node(
        self,
        required_vram: int,
        *,
        prefer_short: bool = False,
        estimated_duration_sec: int | None = None,
        capability: str | None = None,
    ) -> GPUNode:
        """
        按显存需求选空闲节点；全忙则选预计最早空闲的。
        prefer_short / 短任务（<120s）优先占用当前空闲节点，避免被长任务堵死。
        capability：限定节点角色（image / video）；生图必须带 image，避免打到仅视频的 H800。
        """
        is_short = prefer_short
        if estimated_duration_sec is not None:
            is_short = estimated_duration_sec < SHORT_TASK_THRESHOLD_SEC

        with self._lock:
            base = list(self.nodes)
            if capability:
                capped = [n for n in base if capability in n.capabilities]
                if not capped:
                    raise RuntimeError(
                        f"GPUPool 无具备 capability={capability!r} 的节点"
                    )
                base = capped

            eligible = [n for n in base if n.available_vram >= required_vram]
            if not eligible:
                # 无满足显存的节点时，优先显存最大的卡（H800 80G > 5090 32G）
                max_v = max((n.available_vram for n in base), default=0)
                eligible = (
                    [n for n in base if n.available_vram == max_v]
                    if max_v > 0
                    else list(base)
                )
            if not eligible:
                raise RuntimeError("GPUPool 无可用节点")

            free = [n for n in eligible if not n.busy]
            if free:
                return self._pick_free_node_round_robin(free)

            # 全忙：短任务仍选最早空闲，避免无限等待；长任务同样按 ETA
            now = datetime.now(timezone.utc)

            def _eta(n: GPUNode) -> datetime:
                return n.estimated_free_at or now

            # 短任务优先挑 ETA 最近的，减少排队尾延迟
            _ = is_short  # 保留语义位，ETA 策略对长短任务一致
            return min(eligible, key=_eta)

    def mark_busy(
        self,
        node_id: str,
        task_id: str,
        estimated_duration: int,
    ) -> None:
        with self._lock:
            node = self._get(node_id)
            node.busy = True
            node.current_task_id = task_id
            node.estimated_free_at = datetime.now(timezone.utc) + timedelta(
                seconds=max(1, int(estimated_duration))
            )

    def mark_free(self, node_id: str) -> None:
        with self._lock:
            node = self._get(node_id)
            node.busy = False
            node.current_task_id = None
            node.estimated_free_at = None

    def _find_by_url(self, comfyui_url: str) -> GPUNode:
        target = (comfyui_url or "").strip().rstrip("/")
        for n in self.nodes:
            if n.comfyui_url.rstrip("/") == target:
                return n
        raise KeyError(f"unknown comfyui_url={comfyui_url!r}")

    def mark_busy_by_url(
        self,
        comfyui_url: str,
        task_id: str,
        estimated_duration: int,
    ) -> None:
        node = self._find_by_url(comfyui_url)
        self.mark_busy(node.node_id, task_id, estimated_duration)

    def mark_free_by_url(self, comfyui_url: str) -> None:
        node = self._find_by_url(comfyui_url)
        self.mark_free(node.node_id)

    def _get(self, node_id: str) -> GPUNode:
        for n in self.nodes:
            if n.node_id == node_id:
                return n
        raise KeyError(f"unknown node_id={node_id!r}")


_pool: GPUPool | None = None
_pool_lock = threading.Lock()


def get_gpu_pool() -> GPUPool:
    global _pool
    with _pool_lock:
        if _pool is None:
            _pool = GPUPool.from_env()
        return _pool


def reset_gpu_pool_for_tests(pool: GPUPool | None = None) -> GPUPool:
    """测试/探针用：重置或注入池实例。"""
    global _pool
    with _pool_lock:
        _pool = pool if pool is not None else GPUPool.from_env()
        return _pool


def queue_bucket(estimated_duration_sec: int) -> str:
    """short_queue < 120s；long_queue ≥ 120s。"""
    if estimated_duration_sec < SHORT_TASK_THRESHOLD_SEC:
        return "short_queue"
    return "long_queue"


def release_gpu_node(comfyui_url: str | None) -> None:
    """任务终态或取消时释放 GPU 节点占用。"""
    url = (comfyui_url or "").strip().rstrip("/")
    if not url:
        return
    try:
        get_gpu_pool().mark_free_by_url(url)
    except KeyError:
        pass
