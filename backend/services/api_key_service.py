"""RegisteredModel / ModelSetting API Key 加解密读写。"""

from __future__ import annotations

from sqlalchemy.orm import Session

from core.secret_store import decrypt_secret, encrypt_secret
from models import ModelSetting, RegisteredModel


def read_api_key(stored: str | None) -> str | None:
    if not stored or not str(stored).strip():
        return None
    return decrypt_secret(str(stored).strip())


def encrypt_api_key(plain: str | None) -> str | None:
    if plain is None:
        return None
    text = plain.strip()
    if not text:
        return None
    return encrypt_secret(text)


def get_registered_model_api_key(row: RegisteredModel | None) -> str | None:
    if not row:
        return None
    return read_api_key(row.api_key)


def get_model_setting_api_key(db, model_id: str) -> str | None:
    row = db.get(ModelSetting, model_id)
    if not row:
        return None
    return read_api_key(row.api_key)


def migrate_plaintext_api_keys(db: Session) -> int:
    """启动时将明文 API Key 加密入库。"""
    changed = 0
    for row in db.query(RegisteredModel).all():
        raw = (row.api_key or "").strip()
        if not raw or raw.startswith("enc:v1:"):
            continue
        row.api_key = encrypt_secret(raw)
        changed += 1
    for row in db.query(ModelSetting).all():
        raw = (row.api_key or "").strip()
        if not raw or raw.startswith("enc:v1:"):
            continue
        row.api_key = encrypt_secret(raw)
        changed += 1
    if changed:
        db.commit()
    return changed
