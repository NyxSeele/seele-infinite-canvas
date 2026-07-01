"""API Key 等敏感字段的应用层加密（Fernet，密钥由 JWT_SECRET 派生）。"""

from __future__ import annotations

import base64
import hashlib

from cryptography.fernet import Fernet, InvalidToken

from core.config import settings

ENCRYPTED_PREFIX = "enc:v1:"


def _fernet() -> Fernet:
    digest = hashlib.sha256(settings.jwt_secret.encode("utf-8")).digest()
    key = base64.urlsafe_b64encode(digest)
    return Fernet(key)


def encrypt_secret(plain: str | None) -> str | None:
    if plain is None:
        return None
    text = plain.strip()
    if not text:
        return None
    if text.startswith(ENCRYPTED_PREFIX):
        return text
    token = _fernet().encrypt(text.encode("utf-8")).decode("ascii")
    return f"{ENCRYPTED_PREFIX}{token}"


def decrypt_secret(stored: str | None) -> str | None:
    if stored is None:
        return None
    text = stored.strip()
    if not text:
        return None
    if not text.startswith(ENCRYPTED_PREFIX):
        return text
    payload = text[len(ENCRYPTED_PREFIX) :]
    try:
        return _fernet().decrypt(payload.encode("ascii")).decode("utf-8")
    except InvalidToken as exc:
        raise ValueError("无法解密 API Key，请重新配置") from exc


def mask_secret(key: str | None) -> str | None:
    if not key:
        return None
    plain = decrypt_secret(key) or ""
    if not plain:
        return None
    if len(plain) <= 4:
        return "****"
    return f"****{plain[-4:]}"
