"""Seedance compress + registry framework tests."""

from __future__ import annotations

from model_registry import MODEL_MAP, resolve_video_backend
from providers.seedance import SeedanceClient, SeedanceNotConfiguredError
from services.prompt_builder import (
    SEEDANCE_MAX_WORDS,
    SEEDANCE_MIN_WORDS,
    build_prompt,
    compress_for_seedance,
)
import pytest


def test_seedance_registry_disabled():
    entry = MODEL_MAP["seedance-2.0"]
    assert entry["type"] == "api"
    assert entry["video_backend"] == "seedance"
    assert entry["default_enabled"] is False
    assert resolve_video_backend("seedance-2.0") == "seedance"


def test_compress_for_seedance_word_range():
    long_text = (
        "A highly detailed cinematic masterpiece of a young woman walking through a rainy neon street "
        "at night with intricate reflections on wet asphalt, ultra realistic lighting, best quality, "
        "8k, complex background crowds, shallow depth of field, film grain, volumetric fog"
    )
    result = compress_for_seedance(long_text, camera_move="push_in", shot_scale="medium")
    n = len(result.positive_prompt.split())
    assert SEEDANCE_MIN_WORDS <= n <= SEEDANCE_MAX_WORDS
    assert "push in" in result.positive_prompt.lower()
    assert "medium shot" in result.positive_prompt.lower()


def test_build_prompt_seedance_target():
    result = build_prompt(
        "rainy alley chase",
        model_target="seedance",
        camera_move="track",
        shot_scale="wide",
    )
    n = len(result.positive_prompt.split())
    assert SEEDANCE_MIN_WORDS <= n <= SEEDANCE_MAX_WORDS
    assert "tracking shot" in result.positive_prompt.lower()


def test_seedance_client_init_without_key():
    client = SeedanceClient(api_key="")
    assert client.is_configured() is False
    with pytest.raises(SeedanceNotConfiguredError):
        # sync path via headers
        client._headers()
