"""向后兼容：请优先使用 core.security / core.dependencies / services.auth_service。"""
from core.dependencies import get_current_user, get_optional_user, require_admin
from core.security import (
    PASSWORD_PATTERN,
    USERNAME_PATTERN,
    create_access_token,
    create_refresh_token,
    decode_token,
    hash_password,
    verify_password,
)
from services.auth_service import (
    blacklist_refresh_token,
    build_token_response,
    check_login_lock,
    clear_login_attempts,
    is_refresh_blacklisted,
    login_key,
    record_login_failure,
)

# 旧名兼容
token_response = build_token_response

__all__ = [
    "USERNAME_PATTERN",
    "PASSWORD_PATTERN",
    "hash_password",
    "verify_password",
    "create_access_token",
    "create_refresh_token",
    "decode_token",
    "get_current_user",
    "get_optional_user",
    "require_admin",
    "login_key",
    "check_login_lock",
    "record_login_failure",
    "clear_login_attempts",
    "blacklist_refresh_token",
    "is_refresh_blacklisted",
    "token_response",
    "build_token_response",
]
