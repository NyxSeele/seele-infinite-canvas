"""Tests for stock_material_service."""

from __future__ import annotations

import asyncio
from pathlib import Path
from unittest.mock import AsyncMock, patch

import pytest

from services import stock_material_service


def test_is_mock_stock(monkeypatch):
    monkeypatch.setenv("SHORT_VIDEO_MOCK_STOCK", "1")
    assert stock_material_service.is_mock_stock() is True


def test_mock_search_and_fetch_returns_clip(monkeypatch, tmp_path):
    monkeypatch.setenv("SHORT_VIDEO_MOCK_STOCK", "1")

    def fake_generate(output_path, **kwargs):
        output_path.write_bytes(b"mock-mp4")
        return output_path

    with patch.object(stock_material_service, "_generate_mock_stock_clip", side_effect=fake_generate):
        result = asyncio.run(
            stock_material_service.search_and_fetch(
                "city night",
                duration_sec=2.5,
                aspect="9:16",
                task_dir=tmp_path,
                width=640,
                height=360,
                segment_index=0,
            )
        )
    assert result is not None
    assert result.is_file()


def test_pexels_without_key_returns_none(monkeypatch, tmp_path):
    monkeypatch.delenv("PEXELS_API_KEY", raising=False)
    monkeypatch.delenv("PEXELS_API_KEYS", raising=False)
    monkeypatch.delenv("SHORT_VIDEO_MOCK_STOCK", raising=False)
    result = asyncio.run(
        stock_material_service.search_and_fetch(
            "ocean",
            duration_sec=2.0,
            aspect="16:9",
            task_dir=tmp_path,
            width=1920,
            height=1080,
            segment_index=0,
        )
    )
    assert result is None


def test_pexels_empty_search_returns_none(monkeypatch, tmp_path):
    monkeypatch.setenv("PEXELS_API_KEY", "test-key")
    monkeypatch.delenv("SHORT_VIDEO_MOCK_STOCK", raising=False)
    with patch.object(
        stock_material_service,
        "_search_pexels",
        new=AsyncMock(return_value=None),
    ):
        result = asyncio.run(
            stock_material_service.search_and_fetch(
                "ocean",
                duration_sec=2.0,
                aspect="16:9",
                task_dir=tmp_path,
                width=1920,
                height=1080,
                segment_index=0,
            )
        )
    assert result is None
