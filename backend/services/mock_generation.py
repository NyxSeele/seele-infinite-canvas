"""Mock generation provider — 移除时机：ComfyUI 真实模型接入后。"""

from __future__ import annotations

import asyncio
import json
import logging
import random
import shutil
import uuid
from pathlib import Path

from db.base import SessionLocal
from models.task import Task

logger = logging.getLogger(__name__)

MOCK_PROMPT_ID = "mock"

_BACKEND_DIR = Path(__file__).resolve().parent.parent
ASSETS_DIR = _BACKEND_DIR / "assets" / "mock"
UPLOADS_IMAGES = _BACKEND_DIR / "uploads" / "images"
UPLOADS_VIDEOS = _BACKEND_DIR / "uploads" / "videos"

MOCK_FAILURE_MESSAGE = "Mock 模拟失败（AGENT_MOCK_FAILURE_RATE）"


def _release_task_slots(task: Task) -> None:
    if task.user_id is None:
        return
    from services.generation_slots import release_slots

    release_slots(task.user_id, team_id=task.team_id)


def _ensure_upload_dirs() -> None:
    UPLOADS_IMAGES.mkdir(parents=True, exist_ok=True)
    UPLOADS_VIDEOS.mkdir(parents=True, exist_ok=True)


def _pick_image_asset() -> Path:
    assets = sorted(ASSETS_DIR.glob("placeholder_*.jpg")) + sorted(
        ASSETS_DIR.glob("placeholder_*.png")
    )
    if not assets:
        raise FileNotFoundError(
            f"Mock 占位图缺失: {ASSETS_DIR / 'placeholder_*.jpg'}，"
            f"请运行 backend/scripts/generate_mock_assets.py"
        )
    return random.choice(assets)


def _pick_video_asset() -> Path:
    assets = sorted(ASSETS_DIR.glob("placeholder_video_*.mp4"))
    if not assets:
        raise FileNotFoundError(
            f"Mock 占位视频缺失: {ASSETS_DIR / 'placeholder_video_*.mp4'}，"
            f"请运行 backend/scripts/generate_mock_assets.py"
        )
    return random.choice(assets)


def _record_reference_images(task: Task, reference_images: list[str] | None) -> None:
    """保留 reference_images 参数，写入 prompt_text 末尾供后续排查。"""
    refs = [u for u in (reference_images or []) if u and str(u).strip()]
    if not refs:
        return
    marker = "\n<!-- mock_reference_images:"
    if marker in (task.prompt_text or ""):
        return
    payload = json.dumps(refs, ensure_ascii=False)
    base = (task.prompt_text or "").rstrip()
    task.prompt_text = f"{base}{marker}{payload}-->"


async def run_mock_image_task(
    task_id: str,
    reference_images: list[str] | None,
    failure_rate: float,
) -> None:
    """异步执行 mock 图像生成（保留 reference_images 参数模拟真实接口）。"""
    await asyncio.sleep(random.uniform(2, 3))
    db = SessionLocal()
    try:
        task = db.get(Task, task_id)
        if not task:
            return
        _record_reference_images(task, reference_images)
        if random.random() < max(0.0, min(1.0, failure_rate)):
            task.status = "failed"
            task.error = MOCK_FAILURE_MESSAGE
            _release_task_slots(task)
            db.commit()
            logger.info("mock image task failed task_id=%s", task_id)
            return
        _ensure_upload_dirs()
        src = _pick_image_asset()
        ext = src.suffix.lower() or ".jpg"
        dst_name = f"{uuid.uuid4()}{ext}"
        shutil.copy(src, UPLOADS_IMAGES / dst_name)
        task.status = "completed"
        task.result = f"/api/uploads/images/{dst_name}"
        task.error = None
        _release_task_slots(task)
        db.commit()
        logger.info(
            "mock image task completed task_id=%s refs=%s src=%s",
            task_id,
            len(reference_images or []),
            src.name,
        )
    except Exception:
        db.rollback()
        logger.exception("mock image task error task_id=%s", task_id)
        task = db.get(Task, task_id)
        if task and task.status not in ("completed", "failed"):
            task.status = "failed"
            task.error = "Mock 图像生成内部错误"
            _release_task_slots(task)
            db.commit()
    finally:
        db.close()


async def run_mock_video_task(task_id: str, failure_rate: float) -> None:
    """异步执行 mock 视频生成。"""
    await asyncio.sleep(random.uniform(5, 8))
    db = SessionLocal()
    try:
        task = db.get(Task, task_id)
        if not task:
            return
        if random.random() < max(0.0, min(1.0, failure_rate)):
            task.status = "failed"
            task.error = MOCK_FAILURE_MESSAGE
            _release_task_slots(task)
            db.commit()
            logger.info("mock video task failed task_id=%s", task_id)
            return
        _ensure_upload_dirs()
        src = _pick_video_asset()
        dst_name = f"{uuid.uuid4()}.mp4"
        shutil.copy(src, UPLOADS_VIDEOS / dst_name)
        task.status = "completed"
        task.result = f"/api/uploads/videos/{dst_name}"
        task.error = None
        _release_task_slots(task)
        db.commit()
        logger.info("mock video task completed task_id=%s src=%s", task_id, src.name)
    except Exception:
        db.rollback()
        logger.exception("mock video task error task_id=%s", task_id)
        task = db.get(Task, task_id)
        if task and task.status not in ("completed", "failed"):
            task.status = "failed"
            task.error = "Mock 视频生成内部错误"
            _release_task_slots(task)
            db.commit()
    finally:
        db.close()
