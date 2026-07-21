"""get_prompt_execution_status 轮询降载与瞬态错误容错。"""
from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock, patch

import httpx

from comfyui import client as comfy_client
from services import comfyui_progress as prog


def setup_function():
    prog.clear_progress("poll-p1")
    comfy_client.reset_comfy_poll_throttle_for_tests()


def test_fresh_cache_short_circuits_comfy_http():
    prog.record_progress("poll-p1", 5, 10, node="sampler")
    with patch.object(comfy_client.httpx, "AsyncClient") as mock_client_cls:
        mock_client_cls.side_effect = AssertionError("Comfy HTTP should be skipped")
        result = asyncio.run(
            comfy_client.get_prompt_execution_status("poll-p1", node_url="http://127.0.0.1:8000")
        )
    assert result["status"] == "running"
    assert result["progress"] >= 20
    assert result["error"] is None


def test_comfy_timeout_returns_running_not_failed():
    prog.record_progress("poll-p1", 8, 10, node="sampler")
    # 让缓存过期，确保会尝试打 Comfy
    row = prog.get_progress("poll-p1") or {}
    row["updated_at"] = 0
    with prog._lock:
        prog._by_prompt["poll-p1"] = row

    class FakeAsyncClient:
        def __init__(self, *args, **kwargs):
            pass

        async def __aenter__(self):
            return self

        async def __aexit__(self, *args):
            return False

        async def get(self, url):
            raise httpx.TimeoutException("timeout", request=AsyncMock())

    with patch.object(comfy_client.httpx, "AsyncClient", FakeAsyncClient):
        comfy_client.reset_comfy_poll_throttle_for_tests()
        result = asyncio.run(
            comfy_client.get_prompt_execution_status("poll-p1", node_url="http://127.0.0.1:8000")
        )

    assert result["status"] == "running"
    assert result["error"] is None
    assert result["progress"] >= 70


def test_throttle_skips_back_to_back_comfy_http():
    prog.record_progress("poll-p1", 2, 10, node="sampler")
    calls = {"n": 0}

    class FakeAsyncClient:
        def __init__(self, *args, **kwargs):
            pass

        async def __aenter__(self):
            return self

        async def __aexit__(self, *args):
            return False

        async def get(self, url):
            calls["n"] += 1
            req = AsyncMock()
            resp = AsyncMock()
            resp.status_code = 200
            resp.json.return_value = {"queue_running": [], "queue_pending": []}
            return resp

    with patch.object(comfy_client.httpx, "AsyncClient", FakeAsyncClient):
        comfy_client.reset_comfy_poll_throttle_for_tests()
        # 让缓存过期，迫使走 Comfy HTTP 分支
        row = prog.get_progress("poll-p1") or {}
        row["updated_at"] = 0
        with prog._lock:
            prog._by_prompt["poll-p1"] = row

        first = asyncio.run(
            comfy_client.get_prompt_execution_status("poll-p1", node_url="http://127.0.0.1:8000")
        )
        second = asyncio.run(
            comfy_client.get_prompt_execution_status("poll-p1", node_url="http://127.0.0.1:8000")
        )

    assert first["status"] == "running"
    assert second["status"] == "running"
    assert calls["n"] == 2  # 首次 queue+history；节流内第二次不再打 Comfy
