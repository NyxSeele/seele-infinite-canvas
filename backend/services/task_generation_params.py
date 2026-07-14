"""Helpers to build compact generation_params JSON for tasks."""

from __future__ import annotations

import json
from typing import Any


def dumps_generation_params(params: dict[str, Any] | None) -> str | None:
    if not params:
        return None
    cleaned = {k: v for k, v in params.items() if v is not None}
    if not cleaned:
        return None
    return json.dumps(cleaned, ensure_ascii=False)


def parse_generation_params(raw: str | None) -> dict[str, Any]:
    if not raw:
        return {}
    try:
        data = json.loads(raw)
        if isinstance(data, dict):
            return data
    except (json.JSONDecodeError, TypeError):
        pass
    return {}


def build_image_generation_params(
    *,
    ratio: str | None,
    quality: str | None,
    width: int,
    height: int,
    reference_images: list | None = None,
    use_reactor: bool = False,
    mock: bool = False,
) -> dict[str, Any]:
    refs = reference_images or []
    return {
        "ratio": ratio,
        "quality": quality,
        "width": width,
        "height": height,
        "has_reference": bool(refs),
        "reference_count": len(refs),
        "use_reactor": bool(use_reactor),
        "mock": bool(mock),
    }


def build_video_generation_params(
    *,
    ratio: str | None,
    resolution: str | None,
    duration: int | None,
    mode: str | None,
    width: int | None = None,
    height: int | None = None,
    reference_images: list | None = None,
    use_reactor: bool = False,
    mock: bool = False,
) -> dict[str, Any]:
    refs = reference_images or []
    return {
        "ratio": ratio,
        "resolution": resolution,
        "duration": duration,
        "mode": mode,
        "width": width,
        "height": height,
        "has_reference": bool(refs),
        "reference_count": len(refs),
        "use_reactor": bool(use_reactor),
        "mock": bool(mock),
    }
