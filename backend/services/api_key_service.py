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
    """启动时：明文加密；旧 JWT 派生密文重加密到当前主密钥。"""
    from core.secret_store import ENCRYPTED_PREFIX, decrypt_secret, encrypt_secret

    changed = 0
    for row in db.query(RegisteredModel).all():
        raw = (row.api_key or "").strip()
        if not raw:
            continue
        if not raw.startswith(ENCRYPTED_PREFIX):
            row.api_key = encrypt_secret(raw)
            changed += 1
            continue
        # 已加密：尝试解密再以主密钥重写（幂等；主密钥未变则密文可能变化但明文不变）
        try:
            plain = decrypt_secret(raw)
        except ValueError:
            continue
        if not plain:
            continue
        new_enc = encrypt_secret(plain)
        if new_enc and new_enc != raw:
            row.api_key = new_enc
            changed += 1
    for row in db.query(ModelSetting).all():
        raw = (row.api_key or "").strip()
        if not raw:
            continue
        if not raw.startswith(ENCRYPTED_PREFIX):
            row.api_key = encrypt_secret(raw)
            changed += 1
            continue
        try:
            plain = decrypt_secret(raw)
        except ValueError:
            continue
        if not plain:
            continue
        new_enc = encrypt_secret(plain)
        if new_enc and new_enc != raw:
            row.api_key = new_enc
            changed += 1
    if changed:
        db.commit()
    return changed
