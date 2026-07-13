"""API Key 等敏感字段的应用层加密（Fernet）。

优先使用 API_KEY_ENCRYPT_SECRET；未配置时回退 JWT_SECRET（并打 warning）。
旧密文若用 JWT 派生密钥加密，启动迁移会重加密到当前主密钥。
"""

from __future__ import annotations

import base64
import hashlib
import logging

from cryptography.fernet import Fernet, InvalidToken

from core.config import settings

logger = logging.getLogger(__name__)

ENCRYPTED_PREFIX = "enc:v1:"


def _fernet_from_secret(secret: str) -> Fernet:
    digest = hashlib.sha256(secret.encode("utf-8")).digest()
    key = base64.urlsafe_b64encode(digest)
    return Fernet(key)


def _primary_secret() -> str:
    dedicated = (getattr(settings, "api_key_encrypt_secret", None) or "").strip()
    if dedicated:
        return dedicated
    jwt = (settings.jwt_secret or "").strip()
    if jwt:
        logger.warning(
            "API_KEY_ENCRYPT_SECRET 未配置，回退使用 JWT_SECRET 派生 Fernet 密钥；"
            "生产环境请设置独立的 API_KEY_ENCRYPT_SECRET"
        )
        return jwt
    raise ValueError("缺少 API_KEY_ENCRYPT_SECRET / JWT_SECRET，无法加解密 API Key")


def _legacy_jwt_secret() -> str | None:
    """旧版仅用 JWT_SECRET 派生；若与主密钥不同则作为解密回退。"""
    jwt = (settings.jwt_secret or "").strip()
    if not jwt:
        return None
    primary = (getattr(settings, "api_key_encrypt_secret", None) or "").strip()
    if primary and jwt != primary:
        return jwt
    return None


def _fernet() -> Fernet:
    return _fernet_from_secret(_primary_secret())


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
    except InvalidToken:
        legacy = _legacy_jwt_secret()
        if legacy:
            try:
                return _fernet_from_secret(legacy).decrypt(payload.encode("ascii")).decode(
                    "utf-8"
                )
            except InvalidToken:
                pass
        raise ValueError("无法解密 API Key，请重新配置") from None


def mask_secret(key: str | None) -> str | None:
    if not key:
        return None
    plain = decrypt_secret(key) or ""
    if not plain:
        return None
    if len(plain) <= 4:
        return "****"
    return f"****{plain[-4:]}"
