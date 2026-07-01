"""
扫描 ComfyUI checkpoints，将 LOCAL_MODEL_PRESETS 中实际存在的模型写入 registered_models。
"""

import httpx
from sqlalchemy.orm import Session

from db.session import SessionLocal
from core.comfyui_settings import comfyui_checkpoints_url
from model_checker import _flatten_comfyui_model_list
from model_registry import LOCAL_MODEL_PRESETS
from models import RegisteredModel


async def _fetch_checkpoint_files() -> list[str] | None:
    try:
        async with httpx.AsyncClient(timeout=5.0) as client:
            r = await client.get(comfyui_checkpoints_url())
            if r.status_code != 200:
                return None
            return _flatten_comfyui_model_list(r.json())
    except Exception:
        return None


def _match_checkpoint_file(preset_file: str, available_files: list[str]) -> str | None:
    """按去掉扩展名后的前缀模糊匹配，返回实际磁盘上的文件名。"""
    if not preset_file:
        return None
    base_name = preset_file.rsplit(".", 1)[0]
    for f in available_files:
        if base_name in f:
            return f
    return None


def _sync_with_files(db: Session, available_files: list[str]) -> int:
    inserted = 0
    for preset in LOCAL_MODEL_PRESETS:
        preset_file = preset.get("comfyui_file") or ""
        matched_file = _match_checkpoint_file(preset_file, available_files)
        if not matched_file:
            continue

        existing = db.get(RegisteredModel, preset["id"])
        if existing:
            continue

        db.add(
            RegisteredModel(
                id=preset["id"],
                display_name=preset["display_name"],
                category=preset["category"],
                type=preset["type"],
                provider=preset.get("provider"),
                comfyui_file=matched_file,
                enabled=False,
            )
        )
        inserted += 1

    if inserted:
        db.commit()
    return inserted


async def sync_local_models() -> int:
    """
    查询 ComfyUI checkpoint 列表，将预设中且文件存在的本地模型写入 registered_models。
    ComfyUI 未启动时静默跳过。返回本次新插入条数。
    """
    available_files = await _fetch_checkpoint_files()
    if available_files is None:
        return 0

    db = SessionLocal()
    try:
        return _sync_with_files(db, available_files)
    finally:
        db.close()
