"""G39 AudioGen / sound_note 接线单测（mock，无 GPU）。"""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock, patch

from schemas.tasks import CanvasVideoRequest
from services.audiogen import audiogen_available, audiogen_model_dir
from services.audio_mix import mix_sfx_into_video


def test_canvas_video_request_accepts_sound_note():
    body = CanvasVideoRequest(
        model="wan-2.6",
        prompt="雨中街道",
        node_id="n1",
        sound_note="雨声与远处雷鸣",
    )
    assert body.sound_note == "雨声与远处雷鸣"


def test_audiogen_available_false_without_weights(tmp_path, monkeypatch):
    monkeypatch.setenv("AUDIOGEN_MODEL_DIR", str(tmp_path / "missing"))
    assert audiogen_available() is False
    assert "missing" in str(audiogen_model_dir())


def test_mix_sfx_into_video_invokes_ffmpeg(tmp_path):
    video = tmp_path / "clip.mp4"
    wav = tmp_path / "sfx.wav"
    out = tmp_path / "clip_sfx.mp4"
    video.write_bytes(b"fake")
    wav.write_bytes(b"RIFF")

    fake_proc = MagicMock(returncode=0, stderr="", stdout="")

    def _run(cmd, **kwargs):
        # first call may be has_audio probe; second is mix
        if out not in [Path(c) for c in cmd if isinstance(c, str)]:
            # probe: pretend no audio
            return MagicMock(returncode=1, stderr="Duration: 00:00:05.00", stdout="")
        out.write_bytes(b"mixed")
        return fake_proc

    with (
        patch("services.audio_mix._ffmpeg_executable", return_value="ffmpeg"),
        patch("services.audio_mix.subprocess.run", side_effect=_run),
    ):
        result = mix_sfx_into_video(video, wav, out, volume=0.8)
    assert result == out
    assert out.is_file()
