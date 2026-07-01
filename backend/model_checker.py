"""
registered_models 可用性检测（带 60s 缓存）。
"""

from datetime import datetime, timedelta

import httpx

from core.comfyui_settings import comfyui_checkpoints_url
from services.api_key_service import read_api_key

CACHE_TTL_SECONDS = 60

# {model_id: {"available": bool, "ts": datetime}}
_cache: dict[str, dict] = {}


def clear_cache(model_id: str | None = None) -> None:
    if model_id:
        _cache.pop(model_id, None)
        return
    _cache.clear()


def _is_cache_valid(item: dict | None) -> bool:
    if not item:
        return False
    return datetime.utcnow() - item["ts"] < timedelta(seconds=CACHE_TTL_SECONDS)


def _flatten_comfyui_model_list(raw) -> list[str]:
    """
    兼容 ComfyUI /models/checkpoints 多种返回格式：
    - 格式 C：["a.safetensors", ...]
    - 格式 A：{"checkpoints": ["a.safetensors", ...]}
    - 格式 B：{"checkpoints": {"a.safetensors": {...}, ...}}
    """
    if isinstance(raw, list):
        return [str(item) for item in raw]
    if isinstance(raw, dict):
        val = raw.get("checkpoints", raw)
        if isinstance(val, dict):
            return [str(k) for k in val.keys()]
        if isinstance(val, list):
            return [str(item) for item in val]
    return []


async def _check_local_model(comfyui_file: str | None) -> bool:
    target = (comfyui_file or "").strip()
    if not target:
        return False
    try:
        async with httpx.AsyncClient(timeout=3.0) as client:
            response = await client.get(comfyui_checkpoints_url())
        if response.status_code != 200:
            return False
        raw = response.json()
        files = _flatten_comfyui_model_list(raw)
        return any(target in f for f in files)
    except Exception:
        return False


async def check_registered_model_available(model: dict) -> bool:
    model_id = str(model["id"])
    cached = _cache.get(model_id)
    if _is_cache_valid(cached):
        return cached["available"]

    model_type = (model.get("type") or "").lower()
    if model_type == "api":
        available = bool(read_api_key(model.get("api_key")))
    elif model_type == "local":
        available = await _check_local_model(model.get("comfyui_file"))
    else:
        available = False

    _cache[model_id] = {"available": available, "ts": datetime.utcnow()}
    return available
