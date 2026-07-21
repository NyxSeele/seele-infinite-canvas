"""model_gateway_resolver 单元测试（无真实网络）。"""

import pytest

from models import SystemSetting
from services.model_gateway_resolver import (
    GATEWAY_API_KEY_KEY,
    GATEWAY_BASE_URL_KEY,
    GATEWAY_DEFAULT_MODEL_KEY,
    GATEWAY_ENABLED_KEY,
    resolve_chat_endpoint,
    save_model_gateway_settings,
)


class _FakeRow:
    def __init__(self, **kwargs):
        for k, v in kwargs.items():
            setattr(self, k, v)


@pytest.fixture
def db_session():
    from db.session import SessionLocal

    db = SessionLocal()
    try:
        yield db
    finally:
        for key in (
            GATEWAY_ENABLED_KEY,
            GATEWAY_BASE_URL_KEY,
            GATEWAY_API_KEY_KEY,
            GATEWAY_DEFAULT_MODEL_KEY,
        ):
            row = db.get(SystemSetting, key)
            if row:
                db.delete(row)
        db.commit()
        db.close()


def test_model_row_takes_priority_over_gateway(db_session):
    save_model_gateway_settings(
        db_session,
        enabled=True,
        base_url="https://gateway.example/v1",
        default_model="gpt-global",
        api_key="sk-global",
    )
    row = _FakeRow(
        id="qwen-plus",
        api_base="https://model.example/v1",
        api_key="enc:v1:unused",
        model_string="qwen-plus",
    )

    import services.model_gateway_resolver as mgr

    monkeypatch = pytest.MonkeyPatch()
    monkeypatch.setattr(mgr, "get_registered_model_api_key", lambda r: "sk-row")
    try:
        ep = resolve_chat_endpoint(model_row=row, db=db_session)
    finally:
        monkeypatch.undo()

    assert ep["source"] == "model"
    assert ep["base_url"] == "https://model.example/v1"
    assert ep["api_key"] == "sk-row"
    assert ep["default_model"] == "qwen-plus"


def test_global_gateway_when_model_missing_base(db_session):
    save_model_gateway_settings(
        db_session,
        enabled=True,
        base_url="https://gateway.example/v1",
        default_model="gpt-global",
        api_key="sk-global",
    )
    row = _FakeRow(id="qwen-plus", api_base="", api_key=None, model_string="qwen-plus")

    import services.model_gateway_resolver as mgr

    monkeypatch = pytest.MonkeyPatch()
    monkeypatch.setattr(mgr, "get_registered_model_api_key", lambda r: None)
    try:
        ep = resolve_chat_endpoint(model_row=row, db=db_session)
    finally:
        monkeypatch.undo()

    assert ep["source"] == "global_gateway"
    assert ep["base_url"] == "https://gateway.example/v1"
    assert ep["api_key"] == "sk-global"
    assert ep["default_model"] == "gpt-global"


def test_disabled_gateway_falls_back(db_session):
    save_model_gateway_settings(
        db_session,
        enabled=False,
        base_url="https://gateway.example/v1",
        default_model="gpt-global",
        api_key="sk-global",
    )
    row = _FakeRow(id="qwen-plus", api_base="", api_key=None, model_string="qwen-plus")

    import services.model_gateway_resolver as mgr

    monkeypatch = pytest.MonkeyPatch()
    monkeypatch.setattr(mgr, "get_registered_model_api_key", lambda r: None)
    try:
        ep = resolve_chat_endpoint(model_row=row, db=db_session)
    finally:
        monkeypatch.undo()

    assert ep["source"] == "fallback"
    assert ep["api_key"] == ""
    assert ep["base_url"] == ""


def test_resolve_without_db_uses_gateway_when_enabled(db_session):
    save_model_gateway_settings(
        db_session,
        enabled=True,
        base_url="https://gateway.example/v1",
        default_model="gpt-global",
        api_key="sk-global",
    )
    row = _FakeRow(id="qwen-plus", api_base="", api_key=None, model_string="qwen-plus")

    import services.model_gateway_resolver as mgr

    monkeypatch = pytest.MonkeyPatch()
    monkeypatch.setattr(mgr, "get_registered_model_api_key", lambda r: None)
    try:
        ep = resolve_chat_endpoint(model_row=row, db=None)
    finally:
        monkeypatch.undo()

    assert ep["source"] == "global_gateway"
    assert ep["api_key"] == "sk-global"
