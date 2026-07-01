import re
from datetime import datetime, timedelta, timezone

import bcrypt
import jwt
from fastapi import HTTPException

from core.config import settings

USERNAME_PATTERN = re.compile(r"^[a-zA-Z0-9_]{3,20}$")
PASSWORD_PATTERN = re.compile(r"^(?=.*[a-z])(?=.*[A-Z])(?=.*\d).{8,}$")


def hash_password(password: str) -> str:
    return bcrypt.hashpw(password.encode("utf-8"), bcrypt.gensalt()).decode("utf-8")


def verify_password(password: str, password_hash: str) -> bool:
    return bcrypt.checkpw(password.encode("utf-8"), password_hash.encode("utf-8"))


def validate_password_strength(password: str) -> None:
    if not PASSWORD_PATTERN.match(password):
        raise ValueError("密码至少 8 位，且包含大写字母、小写字母和数字")


def validate_username(username: str) -> None:
    if not USERNAME_PATTERN.match(username):
        raise ValueError("用户名须为 3-20 位字母、数字或下划线")


def _create_token(data: dict, expires_delta: timedelta, token_type: str) -> str:
    payload = data.copy()
    payload.update(
        {
            "type": token_type,
            "exp": datetime.now(timezone.utc) + expires_delta,
            "iat": datetime.now(timezone.utc),
        }
    )
    return jwt.encode(payload, settings.jwt_secret, algorithm=settings.jwt_algorithm)


def create_access_token(user_id: int, username: str, role: str) -> str:
    return _create_token(
        {"sub": str(user_id), "username": username, "role": role},
        timedelta(minutes=settings.access_token_expire_minutes),
        "access",
    )


def create_refresh_token(user_id: int) -> str:
    return _create_token(
        {"sub": str(user_id)},
        timedelta(days=settings.refresh_token_expire_days),
        "refresh",
    )


def decode_token(token: str, expected_type: str) -> dict:
    try:
        payload = jwt.decode(
            token,
            settings.jwt_secret,
            algorithms=[settings.jwt_algorithm],
        )
    except jwt.PyJWTError as exc:
        raise HTTPException(status_code=401, detail="无效或已过期的令牌") from exc
    if payload.get("type") != expected_type:
        raise HTTPException(status_code=401, detail="令牌类型错误")
    return payload
