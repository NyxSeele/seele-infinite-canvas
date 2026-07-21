"""release_stale_active_tasks：超时前必须确认 Comfy 未在跑。"""

from __future__ import annotations

import asyncio
from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock, MagicMock, patch

from services import generation_guard as guard


def _old_task(**kwargs):
    task = MagicMock()
    task.id = kwargs.get("id", "t1")
    task.user_id = 7
    task.team_id = None
    task.task_type = kwargs.get("task_type", "video")
    task.status = "running"
    task.comfyui_prompt_id = kwargs.get("prompt_id", "p1")
    task.comfyui_node_url = "http://127.0.0.1:8000"
    task.created_at = datetime.now(timezone.utc) - timedelta(seconds=2000)
    task.result = None
    task.error = None
    return task


def test_stale_kill_skipped_when_backend_busy():
    task = _old_task()
    db = MagicMock()
    db.query.return_value.filter.return_value.all.return_value = [task]

    with patch("comfyui.client.probe_comfy_prompt_liveness", new_callable=AsyncMock) as probe:
        probe.return_value = {
            "state": "busy",
            "status": "running",
            "result": None,
            "error": None,
        }
        with patch.object(guard, "release_slot_for_task") as release:
            killed = asyncio.run(guard.release_stale_active_tasks(db, 7))
            assert killed == 0
            release.assert_not_called()
            assert task.status == "running"


def test_stale_kill_skipped_when_backend_unreachable():
    task = _old_task()
    db = MagicMock()
    db.query.return_value.filter.return_value.all.return_value = [task]

    with patch("comfyui.client.probe_comfy_prompt_liveness", new_callable=AsyncMock) as probe:
        probe.return_value = {
            "state": "unreachable",
            "status": "running",
            "result": None,
            "error": None,
        }
        killed = asyncio.run(guard.release_stale_active_tasks(db, 7))
        assert killed == 0
        assert task.status == "running"


def test_stale_kill_when_backend_idle():
    task = _old_task()
    db = MagicMock()
    db.query.return_value.filter.return_value.all.return_value = [task]

    with patch("comfyui.client.probe_comfy_prompt_liveness", new_callable=AsyncMock) as probe:
        probe.return_value = {
            "state": "idle",
            "status": "failed",
            "result": None,
            "error": "ComfyUI 中未找到该任务，可能已过期",
        }
        with patch.object(guard, "release_slot_for_task"), patch.object(
            guard, "should_refund_video_quota", return_value=False
        ), patch("services.gpu_pool.release_gpu_node"):
            killed = asyncio.run(guard.release_stale_active_tasks(db, 7))
            assert killed == 1
            assert task.status == "failed"


def test_stale_recovers_completed_result():
    task = _old_task()
    db = MagicMock()
    db.query.return_value.filter.return_value.all.return_value = [task]

    with patch("comfyui.client.probe_comfy_prompt_liveness", new_callable=AsyncMock) as probe:
        probe.return_value = {
            "state": "idle",
            "status": "completed",
            "result": "/api/view?filename=x.mp4",
            "error": None,
        }
        with patch.object(guard, "release_slots"), patch.object(
            guard, "schedule_video_postprocess"
        ), patch("services.gpu_pool.release_gpu_node"):
            killed = asyncio.run(guard.release_stale_active_tasks(db, 7))
            assert killed == 1
            assert task.status == "completed"
            assert task.result == "/api/view?filename=x.mp4"


def test_no_prompt_id_can_timeout_by_age():
    task = _old_task(prompt_id=None)
    task.comfyui_prompt_id = None
    db = MagicMock()
    db.query.return_value.filter.return_value.all.return_value = [task]

    with patch.object(guard, "release_slot_for_task"), patch.object(
        guard, "should_refund_video_quota", return_value=False
    ):
        killed = asyncio.run(guard.release_stale_active_tasks(db, 7))
        assert killed == 1
        assert task.status == "failed"
