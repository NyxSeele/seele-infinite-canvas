"""registered_models 与 model_registry 启动同步。"""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import MagicMock, patch

from services import registered_model_sync as rms


def test_sync_updates_stale_comfyui_file():
    row = SimpleNamespace(
        id="flux-pulid",
        display_name="old",
        category="image",
        type="local",
        provider="comfyui",
        comfyui_file="svdq-int4_r32-flux.1-dev.safetensors",
        enabled=True,
    )
    session = MagicMock()
    session.get.return_value = row

    with (
        patch.object(rms, "SessionLocal", return_value=session),
        patch.object(rms, "weights_ready", return_value=(True, "ok")),
    ):
        changed = rms.sync_registered_models(only={"flux-pulid"})

    assert changed >= 1
    assert row.comfyui_file == "svdq-fp4_r32-flux.1-dev.safetensors"
    session.commit.assert_called_once()


def test_seedvr_3b_only_enables_enhance(monkeypatch):
    monkeypatch.setattr(
        rms,
        "_weight_file_ready",
        lambda path, min_bytes=1: path.name
        in {
            "ema_vae_fp16.safetensors",
            "seedvr2_ema_3b_fp8_e4m3fn.safetensors",
        },
    )
    ok, reason = rms._seedvr_enhance_weights_ready()
    assert ok is True
    assert "3b" in reason
    assert rms.seedvr_available_model_sizes() == ["3b"]
    assert rms.default_seedvr_model_size() == "3b"


def test_weights_ready_reports_missing_file():
    ok, reason = rms.weights_ready("flux-pulid")
    assert isinstance(ok, bool)
    assert isinstance(reason, str)
