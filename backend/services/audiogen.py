"""G39: AudioCraft AudioGen — 英文音效描述 → wav。"""

from __future__ import annotations

import logging
import os
import threading
import uuid
from pathlib import Path

logger = logging.getLogger(__name__)

DEFAULT_MODEL_DIR = Path("/root/autodl-tmp/models/audiogen-medium")
UPLOADS_AUDIO = Path(__file__).resolve().parent.parent / "uploads" / "audio"

_model = None
_model_lock = threading.Lock()


def audiogen_model_dir() -> Path:
    raw = (os.environ.get("AUDIOGEN_MODEL_DIR") or "").strip()
    return Path(raw) if raw else DEFAULT_MODEL_DIR


def audiogen_available() -> bool:
    root = audiogen_model_dir()
    if not root.is_dir():
        return False
    # Hub layout: state_dict.bin + compression_state_dict.bin
    return (root / "state_dict.bin").is_file() or any(root.glob("*.bin"))


def _load_model():
    global _model
    with _model_lock:
        if _model is not None:
            return _model
        if not audiogen_available():
            raise RuntimeError(
                f"AudioGen 权重未就绪: {audiogen_model_dir()} "
                "(需 state_dict.bin / compression_state_dict.bin)"
            )
        from audiocraft.models import AudioGen

        device = "cuda" if _cuda_available() else "cpu"
        path = str(audiogen_model_dir().resolve())
        logger.info("Loading AudioGen from %s device=%s", path, device)
        _model = AudioGen.get_pretrained(path, device=device)
        return _model


def _cuda_available() -> bool:
    try:
        import torch

        return bool(torch.cuda.is_available())
    except Exception:
        return False


def generate_sfx_wav(
    english_prompt: str,
    *,
    duration: float = 5.0,
    output_path: Path | None = None,
) -> Path:
    """同步生成音效 wav（英文 prompt）。调用方应放在线程池。"""
    text = (english_prompt or "").strip()
    if not text:
        raise ValueError("音效描述不能为空")
    dur = float(duration)
    if dur < 0.5 or dur > 30.0:
        raise ValueError("duration 须在 0.5–30 秒")

    model = _load_model()
    model.set_generation_params(duration=dur)

    out = output_path
    if out is None:
        UPLOADS_AUDIO.mkdir(parents=True, exist_ok=True)
        out = UPLOADS_AUDIO / f"sfx_{uuid.uuid4().hex}.wav"
    else:
        out = Path(out)
        out.parent.mkdir(parents=True, exist_ok=True)

    wav = model.generate([text])
    one = wav[0].detach().cpu()
    try:
        from audiocraft.data.audio import audio_write

        # audio_write 会追加 .wav；传入无后缀 stem
        stem = out.with_suffix("")
        audio_write(
            str(stem),
            one,
            model.sample_rate,
            strategy="loudness",
            loudness_compressor=True,
        )
        written = Path(str(stem) + ".wav")
        if written != out and written.is_file():
            if out.exists():
                out.unlink()
            written.rename(out)
    except Exception:
        import torchaudio

        torchaudio.save(str(out), one if one.dim() == 2 else one.unsqueeze(0), model.sample_rate)

    if not out.is_file():
        raise RuntimeError(f"AudioGen 未写出文件: {out}")
    logger.info("AudioGen wrote %s (%.1fs) prompt=%r", out, dur, text[:80])
    return out


def unload_model() -> None:
    global _model
    with _model_lock:
        _model = None
