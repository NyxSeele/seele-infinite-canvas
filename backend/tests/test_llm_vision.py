"""视觉 LLM 路由与画风任务回收测试。"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

from services.llm_vision import (
    build_vision_user_content,
    ensure_vision_model_registered,
    model_supports_vision,
)
from services.style_ref_task_recovery import (
    RECOVERY_ERROR,
    recover_orphaned_style_ref_tasks_on_boot,
    recover_stale_style_ref_tasks,
)


def test_model_supports_vision_patterns():
    assert model_supports_vision(
        SimpleNamespace(
            id="qwen-vl-max",
            category="text",
            type="api",
            model_string="qwen-vl-max",
            display_name="Qwen VL",
        )
    )
    assert model_supports_vision(
        SimpleNamespace(
            id="gpt-4o",
            category="text",
            type="api",
            model_string="gpt-4o",
            display_name="GPT-4o",
        )
    )
    assert not model_supports_vision(
        SimpleNamespace(
            id="qwen3-7-max",
            category="text",
            type="api",
            model_string="qwen3.7-max",
            display_name="Qwen Text",
        )
    )


def test_build_vision_user_content_openai():
    parts = build_vision_user_content("describe", "data:image/jpeg;base64,abc")
    assert parts[0]["type"] == "image_url"
    assert parts[1]["type"] == "text"


def test_ensure_vision_model_registered_creates_row(monkeypatch):
    default = SimpleNamespace(
        id="qwen3-7-max-2026-05-17",
        category="text",
        type="api",
        provider="dashscope",
        api_base="https://example.com/v1",
        api_key="enc:key",
        model_string="qwen3.7-max",
        display_name="text",
        enabled=True,
        is_default_text=True,
    )

    class FakeQuery:
        def filter(self, *args, **kwargs):
            return self

        def order_by(self, *args, **kwargs):
            return self

        def all(self):
            return [default]

    class FakeSession:
        def __init__(self):
            self.rows = {}
            self.committed = False

        def get(self, model, key):
            return self.rows.get(key)

        def add(self, row):
            self.rows[row.id] = row

        def commit(self):
            self.committed = True

        def close(self):
            pass

        def query(self, model):
            return FakeQuery()

    fake_db = FakeSession()

    monkeypatch.setattr(
        "services.llm_vision.resolve_vision_model_candidates",
        lambda db=None: [],
    )
    monkeypatch.setattr(
        "services.llm_vision.resolve_text_model",
        lambda db=None: default,
    )
    monkeypatch.setattr(
        "services.llm_vision.get_registered_model_api_key",
        lambda row: "secret",
    )

    created = ensure_vision_model_registered(fake_db)
    assert created is True
    assert fake_db.committed is True
    row = fake_db.rows["qwen-vl-max"]
    assert row.enabled is True
    assert row.model_string == "qwen-vl-max"
    assert fake_db.rows["qwen-vl-max"].api_base == default.api_base


def test_recover_orphaned_style_ref_tasks_on_boot(monkeypatch):
    task = SimpleNamespace(
        status="processing",
        error=None,
        result="partial",
        completed_at=None,
    )
    committed = {"ok": False}

    class FakeQuery:
        def filter(self, *args, **kwargs):
            return self

        def all(self):
            return [task]

    class FakeDB:
        def query(self, model):
            return FakeQuery()

        def commit(self):
            committed["ok"] = True

    count = recover_orphaned_style_ref_tasks_on_boot(FakeDB())
    assert count == 1
    assert task.status == "failed"
    assert task.error == RECOVERY_ERROR
    assert task.result is None
    assert committed["ok"] is True


def test_recover_stale_style_ref_tasks_only_old(monkeypatch):
    old = SimpleNamespace(
        status="processing",
        error=None,
        result=None,
        completed_at=None,
        created_at=datetime.now(timezone.utc) - timedelta(minutes=30),
    )
    fresh = SimpleNamespace(
        status="processing",
        error=None,
        result=None,
        completed_at=None,
        created_at=datetime.now(timezone.utc),
    )
    committed = {"ok": False}

    class FakeQuery:
        def filter(self, *args, **kwargs):
            return self

        def all(self):
            return [old]

    class FakeDB:
        def query(self, model):
            return FakeQuery()

        def commit(self):
            committed["ok"] = True

    count = recover_stale_style_ref_tasks(FakeDB(), max_age_minutes=5)
    assert count == 1
    assert old.status == "failed"
    assert committed["ok"] is True
