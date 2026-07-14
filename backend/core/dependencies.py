from typing import Annotated

from fastapi import Depends, HTTPException, Query
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.orm import Session

from core.security import decode_token
from db.session import get_db
from models import User
from services.media_access import verify_media_ticket

security = HTTPBearer(auto_error=False)


def _user_from_token(token: str, db: Session) -> User | None:
    payload = decode_token(token, "access")
    user_id = int(payload.get("sub", 0))
    return db.get(User, user_id)


def get_current_user(
    credentials: Annotated[HTTPAuthorizationCredentials | None, Depends(security)],
    db: Session = Depends(get_db),
) -> User:
    if not credentials or credentials.scheme.lower() != "bearer":
        raise HTTPException(status_code=401, detail="未登录或令牌缺失")
    user = _user_from_token(credentials.credentials, db)
    if not user:
        raise HTTPException(status_code=401, detail="用户不存在")
    if not user.is_active:
        raise HTTPException(status_code=403, detail="账户已禁用")
    return user


def get_optional_user(
    credentials: Annotated[HTTPAuthorizationCredentials | None, Depends(security)],
    db: Session = Depends(get_db),
) -> User | None:
    if not credentials or credentials.scheme.lower() != "bearer":
        return None
    try:
        user = _user_from_token(credentials.credentials, db)
    except HTTPException:
        return None
    if not user or not user.is_active:
        return None
    return user


def get_media_user(
    credentials: Annotated[HTTPAuthorizationCredentials | None, Depends(security)],
    mt: str | None = Query(None, alias="mt"),
    db: Session = Depends(get_db),
) -> User:
    """媒体 URL 鉴权：Bearer 或短效 mt 票据（video/img 标签无法带 Header）。"""
    if credentials and credentials.scheme.lower() == "bearer":
        return get_current_user(credentials, db)
    uid = verify_media_ticket(mt)
    if uid is None:
        raise HTTPException(status_code=401, detail="未登录或媒体访问票据无效")
    user = db.get(User, uid)
    if not user or not user.is_active:
        raise HTTPException(status_code=401, detail="用户不存在或已禁用")
    return user


def user_from_access_token(token: str, db: Session) -> User:
    if not (token or "").strip():
        raise HTTPException(status_code=401, detail="缺少 token")
    user = _user_from_token(token.strip(), db)
    if not user:
        raise HTTPException(status_code=401, detail="用户不存在")
    if not user.is_active:
        raise HTTPException(status_code=403, detail="账户已禁用")
    return user


def require_admin(user: User = Depends(get_current_user)) -> User:
    if user.role != "admin":
        raise HTTPException(status_code=403, detail="需要管理员权限")
    return user


def require_r2_access(user: User = Depends(get_current_user)) -> User:
    if user.role != "admin" and not getattr(user, "r2_access", False):
        raise HTTPException(status_code=403, detail="未授权访问团队文件空间")
    return user
