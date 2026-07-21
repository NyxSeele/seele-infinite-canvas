"""Edge TTS synthesis for short-video factory segments."""

from __future__ import annotations

import inspect
import os
import re
from pathlib import Path
from typing import Any

import edge_tts
from edge_tts import SubMaker

_DEFAULT_VOICE = "zh-CN-XiaoxiaoNeural"
_MOCK_SECONDS_PER_CHAR = 0.12
_MOCK_MIN_DURATION = 0.8
_SENTENCE_END_RE = re.compile(r"[。！？.!?；;…]\s*$")


def is_mock_tts() -> bool:
    return os.environ.get("SHORT_VIDEO_MOCK_TTS", "").strip().lower() in ("1", "true", "yes")


def rate_to_percent(rate: float) -> str:
    try:
        rate = float(rate)
    except (TypeError, ValueError):
        rate = 1.0
    if rate <= 0:
        rate = 1.0
    percent = round((rate - 1.0) * 100)
    if percent >= 0:
        return f"+{percent}%"
    return f"{percent}%"


def _mock_duration_sec(text: str) -> float:
    cleaned = (text or "").strip()
    if not cleaned:
        return _MOCK_MIN_DURATION
    return max(_MOCK_MIN_DURATION, len(cleaned) * _MOCK_SECONDS_PER_CHAR)


def _write_silent_mp3_placeholder(output_path: Path, duration_sec: float) -> None:
    """Write a real silent audio file so ffmpeg mix/concat does not exit 183 on empty bytes."""
    import shutil
    import subprocess

    output_path.parent.mkdir(parents=True, exist_ok=True)
    dur = max(0.1, float(duration_sec or _MOCK_MIN_DURATION))
    ffmpeg = shutil.which("ffmpeg")
    if not ffmpeg:
        try:
            from services.video_enhance_probe import _ffmpeg_executable

            ffmpeg = _ffmpeg_executable()
        except Exception:
            ffmpeg = None
    if not ffmpeg:
        # Last resort: tiny valid MPEG frame header + padding (not ideal but non-empty)
        output_path.write_bytes(b"\xff\xfb\x90\x00" + b"\x00" * 256)
        return
    cmd = [
        ffmpeg,
        "-y",
        "-f",
        "lavfi",
        "-i",
        "anullsrc=channel_layout=mono:sample_rate=44100",
        "-t",
        f"{dur:.3f}",
        "-q:a",
        "9",
        str(output_path),
    ]
    subprocess.run(
        cmd,
        check=True,
        capture_output=True,
        timeout=60,
    )


def _create_communicate(text: str, voice: str, rate_str: str) -> edge_tts.Communicate:
    kwargs: dict[str, Any] = {"rate": rate_str}
    signature = inspect.signature(edge_tts.Communicate)
    if "boundary" in signature.parameters:
        kwargs["boundary"] = "WordBoundary"
    return edge_tts.Communicate(text, voice, **kwargs)


def _cue_time_seconds(value: Any) -> float:
    if hasattr(value, "total_seconds"):
        return float(value.total_seconds())
    return float(value)


def _aggregate_word_cues_to_sentences(cues: list[Any]) -> list[dict[str, Any]]:
    """Merge word-level edge cues into sentence-level subtitle spans."""
    if not cues:
        return []

    sentences: list[dict[str, Any]] = []
    buffer = ""
    start: float | None = None
    end = 0.0

    for cue in cues:
        piece = str(getattr(cue, "content", "") or "")
        if start is None:
            start = _cue_time_seconds(cue.start)
        end = _cue_time_seconds(cue.end)
        buffer += piece
        if _SENTENCE_END_RE.search(buffer) or len(buffer) >= 40:
            text = buffer.strip()
            if text and start is not None:
                sentences.append({"start": start, "end": end, "text": text})
            buffer = ""
            start = None

    remainder = buffer.strip()
    if remainder and start is not None:
        sentences.append({"start": start, "end": end, "text": remainder})

    return sentences


def cues_from_submaker(sub_maker: SubMaker, fallback_text: str) -> list[dict[str, Any]]:
    raw_cues = list(getattr(sub_maker, "cues", []) or [])
    if raw_cues:
        aggregated = _aggregate_word_cues_to_sentences(raw_cues)
        if aggregated:
            return aggregated

    duration = 0.0
    if raw_cues:
        duration = _cue_time_seconds(raw_cues[-1].end)
    text = (fallback_text or "").strip()
    if not text:
        return []
    if duration <= 0:
        duration = _mock_duration_sec(text)
    return [{"start": 0.0, "end": duration, "text": text}]


async def _synthesize_real(
    text: str,
    *,
    output_path: Path,
    voice: str,
    rate: float,
) -> dict[str, Any]:
    cleaned = (text or "").strip()
    if not cleaned:
        raise ValueError("TTS text 不能为空")

    output_path.parent.mkdir(parents=True, exist_ok=True)
    communicate = _create_communicate(cleaned, voice, rate_to_percent(rate))
    sub_maker = SubMaker()

    with open(output_path, "wb") as audio_file:
        async for chunk in communicate.stream():
            if chunk["type"] == "audio":
                audio_file.write(chunk["data"])
            elif chunk["type"] in ("WordBoundary", "SentenceBoundary"):
                sub_maker.feed(chunk)

    cues = cues_from_submaker(sub_maker, cleaned)
    if cues:
        duration_sec = float(cues[-1]["end"])
    elif output_path.is_file() and output_path.stat().st_size > 0:
        duration_sec = _probe_audio_duration(output_path)
        cues = [{"start": 0.0, "end": duration_sec, "text": cleaned}]
    else:
        raise RuntimeError("Edge TTS 未生成有效音频或字幕时间轴")

    return {
        "audio_path": str(output_path),
        "duration_sec": duration_sec,
        "cues": cues,
    }


def _probe_audio_duration(audio_path: Path) -> float:
    try:
        from services.video_enhance_probe import _ffmpeg_executable

        ffmpeg = _ffmpeg_executable()
        import subprocess

        cmd = [
            ffmpeg,
            "-i",
            str(audio_path),
            "-f",
            "null",
            "-",
        ]
        result = subprocess.run(cmd, capture_output=True, text=True)
        stderr = result.stderr or ""
        for line in stderr.splitlines():
            if "Duration:" in line:
                token = line.split("Duration:", 1)[1].split(",", 1)[0].strip()
                hours, minutes, seconds = token.split(":")
                return int(hours) * 3600 + int(minutes) * 60 + float(seconds)
    except Exception:
        pass
    return _mock_duration_sec(audio_path.name)


async def synthesize_segment(
    text: str,
    *,
    output_path: Path,
    voice: str = _DEFAULT_VOICE,
    rate: float = 1.0,
) -> dict[str, Any]:
    """
    Synthesize one narration segment.

    Returns:
        {
            "audio_path": str,
            "duration_sec": float,
            "cues": [{"start": float, "end": float, "text": str}, ...],
        }
    """
    cleaned = (text or "").strip()
    if not cleaned:
        raise ValueError("segment text 不能为空")

    if is_mock_tts():
        duration_sec = _mock_duration_sec(cleaned)
        _write_silent_mp3_placeholder(output_path, duration_sec)
        return {
            "audio_path": str(output_path),
            "duration_sec": duration_sec,
            "cues": [{"start": 0.0, "end": duration_sec, "text": cleaned}],
        }

    return await _synthesize_real(
        cleaned,
        output_path=output_path,
        voice=voice or _DEFAULT_VOICE,
        rate=rate,
    )
