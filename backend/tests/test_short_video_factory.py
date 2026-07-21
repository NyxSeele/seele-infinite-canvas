"""Short-video factory and postprocess tests."""

from __future__ import annotations

import asyncio
import os
import shutil
import subprocess
from pathlib import Path
from unittest.mock import patch

import pytest

from services import short_video_factory, video_postprocess


def test_generate_segments_mock(monkeypatch):
    monkeypatch.setenv("SHORT_VIDEO_MOCK_LLM", "1")
    segments = asyncio.run(short_video_factory.generate_segments("重庆夜景", segment_count=2))
    assert len(segments) == 2
    assert "重庆夜景" in segments[0].narration


def test_build_factory_video_creates_final(tmp_path, monkeypatch):
    monkeypatch.setenv("SHORT_VIDEO_MOCK_LLM", "1")

    def fake_run(cmd, check=True, capture_output=True, text=True):
        out_idx = cmd.index("-y") + 1 if "-y" in cmd else -1
        output = Path(cmd[-1])
        if output.suffix == ".mp4":
            if "concat" in cmd:
                output.write_bytes(b"final-mp4")
            else:
                output.write_bytes(b"segment-mp4")
        return subprocess.CompletedProcess(cmd, 0, "", "")

    with patch.object(subprocess, "run", side_effect=fake_run):
        segments = asyncio.run(short_video_factory.generate_segments("测试主题", segment_count=2))
        final = asyncio.run(
            short_video_factory.build_factory_video(
                segments,
                task_dir=tmp_path,
                width=640,
                height=360,
                segment_seconds=1.0,
            )
        )
    assert final.is_file()
    assert final.name == "final.mp4"


def test_synthesize_segments_audio_mock_sets_non_uniform_durations(monkeypatch, tmp_path):
    monkeypatch.setenv("SHORT_VIDEO_MOCK_TTS", "1")
    segments = [
        short_video_factory.ShortVideoSegment(narration="短", visual_prompt="a"),
        short_video_factory.ShortVideoSegment(
            narration="这是一段更长的旁白用于测试",
            visual_prompt="b",
        ),
    ]
    updated = asyncio.run(
        short_video_factory.synthesize_segments_audio(
            segments,
            task_dir=tmp_path,
            voice_name="zh-CN-XiaoxiaoNeural",
        )
    )
    assert updated[0].duration_sec is not None
    assert updated[1].duration_sec is not None
    assert updated[1].duration_sec > updated[0].duration_sec
    assert updated[0].audio_path
    assert len(updated[0].cues) == 1


def test_build_timeline_cues_not_uniform_i_times_two(monkeypatch):
    monkeypatch.setenv("SHORT_VIDEO_MOCK_TTS", "1")
    segments = [
        short_video_factory.ShortVideoSegment(narration="短", visual_prompt="a"),
        short_video_factory.ShortVideoSegment(
            narration="这是一段更长的旁白用于测试",
            visual_prompt="b",
        ),
    ]
    segments = asyncio.run(
        short_video_factory.synthesize_segments_audio(
            segments,
            task_dir=Path("/tmp/unused"),
        )
    )
    cues = short_video_factory.build_timeline_cues(segments)
    assert len(cues) >= 2
    assert cues[1]["start"] != 2.0
    total_duration = sum(seg.duration_sec or 0 for seg in segments)
    assert cues[-1]["end"] == pytest.approx(total_duration)


def test_build_factory_video_stock_mock_creates_final(tmp_path, monkeypatch):
    monkeypatch.setenv("SHORT_VIDEO_MOCK_LLM", "1")
    monkeypatch.setenv("SHORT_VIDEO_MOCK_TTS", "1")
    monkeypatch.setenv("SHORT_VIDEO_MOCK_STOCK", "1")

    def fake_run(cmd, check=True, capture_output=True, text=True, timeout=None, **kwargs):
        output = Path(cmd[-1])
        if output.suffix == ".mp4":
            output.write_bytes(b"segment-mp4")
        elif output.suffix in {".mp3", ".wav", ".m4a"}:
            output.write_bytes(b"silent-audio")
        return subprocess.CompletedProcess(cmd, 0, "", "")

    with patch.object(subprocess, "run", side_effect=fake_run):
        segments = asyncio.run(short_video_factory.generate_segments("测试主题", segment_count=2))
        segments = asyncio.run(
            short_video_factory.synthesize_segments_audio(segments, task_dir=tmp_path)
        )
        final = asyncio.run(
            short_video_factory.build_factory_video(
                segments,
                task_dir=tmp_path,
                width=640,
                height=360,
                enable_tts=True,
                visual_source="stock",
            )
        )
    assert final.is_file()
    assert final.name == "final.mp4"


def test_build_factory_video_stock_failure_falls_back_to_slide(tmp_path, monkeypatch):
    monkeypatch.setenv("SHORT_VIDEO_MOCK_LLM", "1")
    monkeypatch.delenv("SHORT_VIDEO_MOCK_STOCK", raising=False)
    monkeypatch.delenv("PEXELS_API_KEY", raising=False)

    def fake_run(cmd, check=True, capture_output=True, text=True):
        output = Path(cmd[-1])
        if output.suffix == ".png":
            output.write_bytes(b"png")
        if output.suffix == ".mp4":
            output.write_bytes(b"segment-mp4")
        return subprocess.CompletedProcess(cmd, 0, "", "")

    with patch.object(subprocess, "run", side_effect=fake_run):
        segments = asyncio.run(short_video_factory.generate_segments("测试主题", segment_count=2))
        final = asyncio.run(
            short_video_factory.build_factory_video(
                segments,
                task_dir=tmp_path,
                width=640,
                height=360,
                visual_source="stock",
            )
        )
    assert final.is_file()
    assert (tmp_path / "slide_00.png").is_file()


def test_build_uniform_cues_legacy_path():
    segments = [
        short_video_factory.ShortVideoSegment(narration="a", visual_prompt="a"),
        short_video_factory.ShortVideoSegment(narration="b", visual_prompt="b"),
    ]
    cues = short_video_factory.build_uniform_cues(segments, segment_seconds=2.0)
    assert cues[0]["start"] == 0.0
    assert cues[0]["end"] == 2.0
    assert cues[1]["start"] == 2.0
    assert cues[1]["end"] == 4.0


def test_burn_subtitles_no_cues_copies(tmp_path):
    src = tmp_path / "src.mp4"
    dst = tmp_path / "dst.mp4"
    src.write_bytes(b"video")
    video_postprocess.burn_subtitles(src, [], dst)
    assert dst.read_bytes() == b"video"


def test_mix_bgm_missing_skips(tmp_path):
    src = tmp_path / "src.mp4"
    dst = tmp_path / "dst.mp4"
    src.write_bytes(b"video")
    video_postprocess.mix_bgm(src, tmp_path / "missing.mp3", dst)
    assert dst.read_bytes() == b"video"


def test_burn_subtitles_builds_drawtext_command(tmp_path, monkeypatch):
    src = tmp_path / "src.mp4"
    dst = tmp_path / "dst.mp4"
    src.write_bytes(b"video")
    captured: dict[str, list[str]] = {}

    def fake_run(cmd, check=True, capture_output=True, text=True):
        captured["cmd"] = cmd
        dst.write_bytes(b"captioned")
        return subprocess.CompletedProcess(cmd, 0, "", "")

    monkeypatch.setattr(video_postprocess.subprocess, "run", fake_run)
    video_postprocess.burn_subtitles(
        src,
        [{"text": "Hello", "start": 0.0, "end": 1.5}],
        dst,
    )
    assert dst.is_file()
    assert "drawtext" in " ".join(captured["cmd"])
