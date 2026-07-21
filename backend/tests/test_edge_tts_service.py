"""Tests for edge_tts_service."""

from __future__ import annotations

import asyncio
from pathlib import Path

import pytest

from services import edge_tts_service


def test_mock_synthesize_segment_duration_scales_with_text(monkeypatch, tmp_path):
    monkeypatch.setenv("SHORT_VIDEO_MOCK_TTS", "1")
    short = asyncio.run(
        edge_tts_service.synthesize_segment(
            "短",
            output_path=tmp_path / "a.mp3",
        )
    )
    long = asyncio.run(
        edge_tts_service.synthesize_segment(
            "这是一段明显更长的旁白文本",
            output_path=tmp_path / "b.mp3",
        )
    )
    assert long["duration_sec"] > short["duration_sec"]
    assert short["cues"][0]["start"] == 0.0
    assert short["cues"][0]["end"] == pytest.approx(short["duration_sec"])
    assert short["cues"][0]["text"] == "短"


def test_mock_cues_align_with_duration(monkeypatch, tmp_path):
    monkeypatch.setenv("SHORT_VIDEO_MOCK_TTS", "1")
    result = asyncio.run(
        edge_tts_service.synthesize_segment(
            "Velora 探针",
            output_path=tmp_path / "probe.mp3",
        )
    )
    cue_span = result["cues"][0]["end"] - result["cues"][0]["start"]
    assert cue_span == pytest.approx(result["duration_sec"])


def test_rate_to_percent_handles_edge_cases():
    assert edge_tts_service.rate_to_percent(1.0) == "+0%"
    assert edge_tts_service.rate_to_percent(1.2) == "+20%"
    assert edge_tts_service.rate_to_percent(0.8) == "-20%"
    assert edge_tts_service.rate_to_percent(0) == "+0%"
