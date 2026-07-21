import hashlib
import json
import time

from fastapi import HTTPException, Request
from sqlalchemy.orm import Session

from core.config import settings
from core.security import (
    create_access_token,
    create_refresh_token,
    decode_token,
    hash_password,
    validate_password_strength,
    validate_username,
    verify_password,
)
from models import QuotaPlan, User, UserQuota, utcnow
from models.quota import first_day_of_month
from schemas.auth import TokenResponse, UserInfo
from services.quota_service import get_quota_info
from services.rate_limit import check_login_ip_rate_limit
from services.redis_client import get_redis

_login_attempts: dict[str, dict] = {}
_refresh_blacklist: set[str] = set()

_LOGIN_KEY = "auth:login:{key}"
_REFRESH_BL_KEY = "auth:refresh:bl:{digest}"


def login_key(username_or_email: str) -> str:
    return username_or_email.strip().lower()


def _login_redis_key(key: str) -> str:
    return _LOGIN_KEY.format(key=key)


def _refresh_digest(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def check_login_lock(key: str) -> None:
    r = get_redis()
    if r is not None:
        raw = r.get(_login_redis_key(key))
        if raw:
            try:
                record = json.loads(raw)
            except json.JSONDecodeError:
                record = {}
            locked_until = float(record.get("locked_until", 0))
            if time.time() < locked_until:
                remaining = int(locked_until - time.time())
                raise HTTPException(
                    status_code=429,
                    detail=f"登录尝试过多，请 {remaining // 60 + 1} 分钟后再试",
                )
        return
    record = _login_attempts.get(key)
    if not record:
        return
    locked_until = record.get("locked_until", 0)
    if time.time() < locked_until:
        remaining = int(locked_until - time.time())
        raise HTTPException(
            status_code=429,
            detail=f"登录尝试过多，请 {remaining // 60 + 1} 分钟后再试",
        )


def record_login_failure(key: str) -> None:
    r = get_redis()
    if r is not None:
        rk = _login_redis_key(key)
        raw = r.get(rk)
        record = {"count": 0, "locked_until": 0}
        if raw:
            try:
                record = json.loads(raw)
            except json.JSONDecodeError:
                pass
        record["count"] = int(record.get("count", 0)) + 1
        max_fail = int(settings.login_max_failures)
        lock_sec = int(settings.login_lock_minutes) * 60
        if record["count"] >= max_fail:
            record["locked_until"] = time.time() + lock_sec
            record["count"] = 0
        r.set(rk, json.dumps(record), ex=max(lock_sec, 15 * 60))
        return
    record = _login_attempts.setdefault(key, {"count": 0, "locked_until": 0})
    record["count"] = record.get("count", 0) + 1
    max_fail = int(settings.login_max_failures)
    lock_sec = int(settings.login_lock_minutes) * 60
    if record["count"] >= max_fail:
        record["locked_until"] = time.time() + lock_sec
        record["count"] = 0


def clear_login_attempts(key: str) -> None:
    r = get_redis()
    if r is not None:
        r.delete(_login_redis_key(key))
        return
    _login_attempts.pop(key, None)


def blacklist_refresh_token(refresh_token: str) -> None:
    r = get_redis()
    ttl = int(settings.refresh_token_expire_days) * 86400
    digest = _refresh_digest(refresh_token)
    if r is not None:
        r.set(_REFRESH_BL_KEY.format(digest=digest), "1", ex=ttl)
        return
    _refresh_blacklist.add(refresh_token)


def is_refresh_blacklisted(refresh_token: str) -> bool:
    r = get_redis()
    digest = _refresh_digest(refresh_token)
    if r is not None:
        return bool(r.get(_REFRESH_BL_KEY.format(digest=digest)))
    return refresh_token in _refresh_blacklist


def _assign_quota(
    db: Session,
    user_id: int,
    image_limit: int = 50,
    video_limit: int = 10,
    plan_name: str = "default",
) -> None:
    db.add(
        UserQuota(
            user_id=user_id,
            plan_name=plan_name,
            image_limit=image_limit,
            video_limit=video_limit,
            image_used=0,
            video_used=0,
            period_start=first_day_of_month(),
        )
    )


def build_token_response(user: User) -> dict:
    return TokenResponse(
        access_token=create_access_token(user.id, user.username, user.role),
        refresh_token=create_refresh_token(user.id),
        user=UserInfo(
            id=user.id,
            username=user.username,
            role=user.role,
            r2_access=bool(getattr(user, "r2_access", False)),
        ),
    ).model_dump()


def register(db: Session, username: str, email: str, password: str, invite_code: str) -> dict:
    username = username.strip()
    email = email.strip().lower()
    expected = (settings.registration_invite_code or "").strip()
    if expected and invite_code.strip() != expected:
        raise HTTPException(status_code=403, detail="邀请码无效")

    try:
        validate_username(username)
        validate_password_strength(password)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e

    if db.query(User).filter(User.username == username).first():
        raise HTTPException(status_code=400, detail="用户名已被占用")
    if db.query(User).filter(User.email == email).first():
        raise HTTPException(status_code=400, detail="邮箱已被注册")

    if not db.query(QuotaPlan).filter(QuotaPlan.name == "default").first():
        raise HTTPException(status_code=500, detail="系统未初始化配额计划")

    user = User(
        username=username,
        email=email,
        password_hash=hash_password(password),
        role="user",
        is_active=True,
        r2_access=True,
    )
    db.add(user)
    db.flush()
    _assign_quota(db, user.id)
    db.commit()
    db.refresh(user)
    return build_token_response(user)


def login(db: Session, username_or_email: str, password: str, request: Request | None = None) -> dict:
    if request is not None:
        check_login_ip_rate_limit(request)
    key = login_key(username_or_email)
    check_login_lock(key)

    ident = username_or_email.strip()
    user = (
        db.query(User)
        .filter((User.username == ident) | (User.email == ident.lower()))
        .first()
    )

    if not user or not verify_password(password, user.password_hash):
        record_login_failure(key)
        raise HTTPException(status_code=401, detail="用户名或密码错误")

    if not user.is_active:
        raise HTTPException(status_code=403, detail="账户已禁用")

    clear_login_attempts(key)
    user.last_login_at = utcnow()
    db.commit()
    db.refresh(user)
    return build_token_response(user)


def refresh_access_token(db: Session, refresh_token: str) -> dict:
    if is_refresh_blacklisted(refresh_token):
        raise HTTPException(status_code=401, detail="令牌已失效，请重新登录")
    payload = decode_token(refresh_token, "refresh")
    user_id = int(payload.get("sub", 0))
    user = db.get(User, user_id)
    if not user or not user.is_active:
        raise HTTPException(status_code=401, detail="用户不存在或已禁用")
    return {
        "access_token": create_access_token(user.id, user.username, user.role),
        "token_type": "bearer",
    }


def _profile_dict(user: User) -> dict:
    return {
        "id": user.id,
        "username": user.username,
        "email": user.email,
        "role": user.role,
        "avatar_url": user.avatar_url or "",
        "display_name": user.display_name or "",
        "bio": user.bio or "",
        "r2_access": bool(getattr(user, "r2_access", False)),
        "quota": None,
    }


def get_me(db: Session, user: User) -> dict:
    data = _profile_dict(user)
    data["quota"] = get_quota_info(db, user.id)
    return data


def _normalize_avatar_url(url: str | None) -> str | None:
    raw = (url or "").strip()
    if not raw:
        return None
    if "?" in raw:
        raw = raw.split("?", 1)[0]
    if raw.startswith("http://") or raw.startswith("https://"):
        from services.r2 import ensure_encoded_r2_public_url, is_r2_public_asset_url

        if is_r2_public_asset_url(raw):
            return ensure_encoded_r2_public_url(raw)
        from urllib.parse import urlparse

        parsed = urlparse(raw)
        raw = parsed.path or ""
    if not raw.startswith("/api/uploads/images/"):
        raise HTTPException(status_code=400, detail="头像地址无效")
    filename = raw.rsplit("/", 1)[-1]
    if not filename or len(filename) > 200:
        raise HTTPException(status_code=400, detail="头像地址无效")
    return raw


def update_profile(
    db: Session,
    user: User,
    *,
    display_name: str | None = None,
    bio: str | None = None,
    avatar_url: str | None = None,
    clear_avatar: bool = False,
) -> dict:
    if display_name is not None:
        user.display_name = display_name.strip()[:64] or None
    if bio is not None:
        user.bio = bio.strip()[:500] or None
    if clear_avatar:
        user.avatar_url = None
    elif avatar_url is not None:
        user.avatar_url = _normalize_avatar_url(avatar_url)
    db.commit()
    db.refresh(user)
    return get_me(db, user)
