"""文本 LLM endpoint 解析：行级 api_base → 全局 Model Gateway → fallback。"""

from __future__ import annotations

from sqlalchemy.orm import Session

from core.secret_store import decrypt_secret, encrypt_secret, mask_secret
from models import RegisteredModel, SystemSetting
from services.api_key_service import get_registered_model_api_key

GATEWAY_ENABLED_KEY = "model_gateway_enabled"
GATEWAY_BASE_URL_KEY = "model_gateway_base_url"
GATEWAY_API_KEY_KEY = "model_gateway_api_key"
GATEWAY_DEFAULT_MODEL_KEY = "model_gateway_default_model"


def _get_setting(db: Session | None, key: str) -> str | None:
    if db is None:
        return None
    row = db.get(SystemSetting, key)
    if not row or row.value is None:
        return None
    return str(row.value)


def _is_truthy(value: str | None) -> bool:
    return (value or "").strip().lower() in {"true", "1", "yes", "on"}


def get_gateway_api_key(db: Session | None) -> str | None:
    stored = _get_setting(db, GATEWAY_API_KEY_KEY)
    if not stored:
        return None
    try:
        return decrypt_secret(stored)
    except ValueError:
        return None


def get_model_gateway_settings(db: Session) -> dict:
    enabled = _is_truthy(_get_setting(db, GATEWAY_ENABLED_KEY))
    base_url = (_get_setting(db, GATEWAY_BASE_URL_KEY) or "").strip()
    default_model = (_get_setting(db, GATEWAY_DEFAULT_MODEL_KEY) or "").strip()
    stored_key = _get_setting(db, GATEWAY_API_KEY_KEY)
    return {
        "enabled": enabled,
        "base_url": base_url,
        "default_model": default_model,
        "api_key_masked": mask_secret(stored_key),
    }


def save_model_gateway_settings(
    db: Session,
    *,
    enabled: bool,
    base_url: str | None,
    default_model: str | None,
    api_key: str | None = None,
    clear_api_key: bool = False,
) -> dict:
    def upsert(key: str, value: str | None) -> None:
        row = db.get(SystemSetting, key)
        if row is None:
            row = SystemSetting(key=key, value=value)
            db.add(row)
        else:
            row.value = value

    upsert(GATEWAY_ENABLED_KEY, "true" if enabled else "false")
    upsert(GATEWAY_BASE_URL_KEY, (base_url or "").strip() or None)
    upsert(GATEWAY_DEFAULT_MODEL_KEY, (default_model or "").strip() or None)

    if clear_api_key:
        upsert(GATEWAY_API_KEY_KEY, None)
    elif api_key is not None and api_key.strip():
        upsert(GATEWAY_API_KEY_KEY, encrypt_secret(api_key.strip()))

    db.commit()
    return get_model_gateway_settings(db)


def resolve_chat_endpoint(*, model_row: RegisteredModel | None = None, db=None) -> dict:
    """返回 {base_url, api_key, default_model, source}。"""
    if db is None:
        from db.session import SessionLocal

        session = SessionLocal()
        try:
            return _resolve_chat_endpoint_impl(model_row=model_row, db=session)
        finally:
            session.close()
    return _resolve_chat_endpoint_impl(model_row=model_row, db=db)


def _resolve_chat_endpoint_impl(*, model_row: RegisteredModel | None = None, db) -> dict:
    """返回 {base_url, api_key, default_model, source}。"""
    row_model = ""
    if model_row is not None:
        row_model = (getattr(model_row, "model_string", None) or model_row.id or "").strip()

    if model_row is not None:
        api_key = get_registered_model_api_key(model_row)
        base = (model_row.api_base or "").strip()
        if api_key and base:
            return {
                "base_url": base,
                "api_key": api_key,
                "default_model": row_model,
                "source": "model",
            }

    if db is not None and _is_truthy(_get_setting(db, GATEWAY_ENABLED_KEY)):
        base_url = (_get_setting(db, GATEWAY_BASE_URL_KEY) or "").strip()
        api_key = get_gateway_api_key(db)
        default_model = (_get_setting(db, GATEWAY_DEFAULT_MODEL_KEY) or "").strip() or row_model
        if base_url and api_key:
            return {
                "base_url": base_url,
                "api_key": api_key,
                "default_model": default_model,
                "source": "global_gateway",
            }

    return {
        "base_url": "",
        "api_key": "",
        "default_model": row_model,
        "source": "fallback",
    }
