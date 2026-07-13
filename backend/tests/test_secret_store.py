"""API Key Fernet 加解密与迁移单测。"""

from __future__ import annotations

import pytest

from core import secret_store
from core.secret_store import ENCRYPTED_PREFIX, decrypt_secret, encrypt_secret


def test_encrypt_decrypt_roundtrip(monkeypatch):
    monkeypatch.setattr(secret_store.settings, "api_key_encrypt_secret", "unit-test-api-key-secret-32")
    monkeypatch.setattr(secret_store.settings, "jwt_secret", "unit-test-jwt-secret-xxxx")
    enc = encrypt_secret("sk-test-plain-key")
    assert enc and enc.startswith(ENCRYPTED_PREFIX)
    assert decrypt_secret(enc) == "sk-test-plain-key"


def test_plaintext_passthrough_on_decrypt(monkeypatch):
    monkeypatch.setattr(secret_store.settings, "api_key_encrypt_secret", "unit-test-api-key-secret-32")
    assert decrypt_secret("already-plain") == "already-plain"


def test_legacy_jwt_ciphertext_redecrypt(monkeypatch):
    """旧密文用 JWT 派生；主密钥改为 API_KEY_ENCRYPT_SECRET 后仍可解。"""
    monkeypatch.setattr(secret_store.settings, "api_key_encrypt_secret", "")
    monkeypatch.setattr(secret_store.settings, "jwt_secret", "legacy-jwt-secret-16chars")
    old_enc = encrypt_secret("dashscope-old")
    assert old_enc.startswith(ENCRYPTED_PREFIX)

    monkeypatch.setattr(secret_store.settings, "api_key_encrypt_secret", "new-dedicated-secret-16x")
    assert decrypt_secret(old_enc) == "dashscope-old"
    new_enc = encrypt_secret("dashscope-old")
    assert new_enc != old_enc
    assert decrypt_secret(new_enc) == "dashscope-old"
