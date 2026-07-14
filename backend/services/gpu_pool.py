"""多 ComfyUI / GPU 节点池（单机亦可，仅解析 COMFYUI_NODES）。"""

from __future__ import annotations

import os
import threading
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from typing import Optional

SHORT_TASK_THRESHOLD_SEC = 120


@dataclass
class GPUNode:
    node_id: str
    comfyui_url: str  # 如 http://127.0.0.1:8000
    available_vram: int  # GB
    busy: bool = False
    current_task_id: Optional[str] = None
    estimated_free_at: Optional[datetime] = None


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
        urls: list[str] = []
        try:
            from core.comfyui_settings import comfyui_nodes_list

            urls = comfyui_nodes_list()
        except Exception:
            urls = []

        if not urls:
            raw = (os.environ.get(env_var) or "").strip()
            if not raw:
                raw = (
                    os.environ.get("COMFYUI_URL")
                    or os.environ.get("COMFYUI_BASE")
                    or fallback_url
                ).strip()
            urls = [u.strip().rstrip("/") for u in raw.split(",") if u.strip()]
        if not urls:
            urls = [fallback_url.rstrip("/")]
        nodes = [
            GPUNode(
                node_id=f"gpu-{i}",
                comfyui_url=url,
                available_vram=default_vram_gb,
            )
            for i, url in enumerate(urls)
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
    ) -> GPUNode:
        """
        按显存需求选空闲节点；全忙则选预计最早空闲的。
        prefer_short / 短任务（<120s）优先占用当前空闲节点，避免被长任务堵死。
        """
        is_short = prefer_short
        if estimated_duration_sec is not None:
            is_short = estimated_duration_sec < SHORT_TASK_THRESHOLD_SEC

        with self._lock:
            eligible = [n for n in self.nodes if n.available_vram >= required_vram]
            if not eligible:
                eligible = list(self.nodes)
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
