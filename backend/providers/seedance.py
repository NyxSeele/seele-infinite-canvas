"""Volcengine Ark Seedance 2.0 异步视频 API 客户端（无 Key 时可安全初始化）。"""

from __future__ import annotations

import os
from typing import Any

import httpx

DEFAULT_API_BASE = "https://ark.cn-beijing.volces.com/api/v3"
DEFAULT_MODEL_ID = "doubao-seedance-2-0-260128"


class SeedanceNotConfiguredError(RuntimeError):
    """未配置 SEEDANCE_API_KEY。"""


class SeedanceClient:
    """Ark contents/generations 异步任务客户端。"""

    def __init__(
        self,
        api_key: str | None = None,
        api_base: str | None = None,
        model_id: str | None = None,
    ) -> None:
        self.api_key = (api_key if api_key is not None else os.getenv("SEEDANCE_API_KEY", "")).strip()
        self.api_base = (
            api_base
            if api_base is not None
            else os.getenv("SEEDANCE_API_BASE", DEFAULT_API_BASE)
        ).rstrip("/")
        self.model_id = (
            model_id
            if model_id is not None
            else os.getenv("SEEDANCE_MODEL_ID", DEFAULT_MODEL_ID)
        ).strip() or DEFAULT_MODEL_ID

    def is_configured(self) -> bool:
        return bool(self.api_key)

    def _headers(self) -> dict[str, str]:
        if not self.api_key:
            raise SeedanceNotConfiguredError("未配置 SEEDANCE_API_KEY")
        return {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
        }

    async def create_task(
        self,
        prompt: str,
        *,
        ratio: str = "16:9",
        duration: int = 5,
        resolution: str = "720p",
        watermark: bool = False,
    ) -> dict[str, Any]:
        """POST /contents/generations/tasks → 返回含 id 的任务对象。"""
        payload = {
            "model": self.model_id,
            "content": [{"type": "text", "text": str(prompt).strip()}],
            "ratio": ratio,
            "duration": int(duration),
            "resolution": str(resolution).lower().replace("p", "p") if resolution else "720p",
            "watermark": watermark,
        }
        # normalize 1080P → 1080p
        res = str(resolution or "720p").strip().lower()
        if res.endswith("p") and res[:-1].isdigit():
            payload["resolution"] = res
        elif res.upper() in ("720P", "1080P"):
            payload["resolution"] = res.lower()
        else:
            payload["resolution"] = "720p"

        async with httpx.AsyncClient(timeout=60.0) as client:
            resp = await client.post(
                f"{self.api_base}/contents/generations/tasks",
                headers=self._headers(),
                json=payload,
            )
            resp.raise_for_status()
            return resp.json()

    async def get_task(self, task_id: str) -> dict[str, Any]:
        """GET /contents/generations/tasks/{id}"""
        async with httpx.AsyncClient(timeout=60.0) as client:
            resp = await client.get(
                f"{self.api_base}/contents/generations/tasks/{task_id}",
                headers=self._headers(),
            )
            resp.raise_for_status()
            return resp.json()
