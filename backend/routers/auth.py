from fastapi import APIRouter, Depends, Request
from sqlalchemy.orm import Session

from core.dependencies import get_current_user
from db.session import get_db
from models import User
from schemas.auth import LoginRequest, LogoutRequest, ProfileUpdateRequest, RefreshRequest, RegisterRequest
from services import auth_service

router = APIRouter(prefix="/api/auth", tags=["auth"])


@router.post("/register")
def register(body: RegisterRequest, db: Session = Depends(get_db)):
    return auth_service.register(
        db, body.username, str(body.email), body.password
    )


@router.post("/login")
def login(body: LoginRequest, request: Request, db: Session = Depends(get_db)):
    return auth_service.login(db, body.username_or_email, body.password, request)


@router.post("/refresh")
def refresh_token(body: RefreshRequest, db: Session = Depends(get_db)):
    return auth_service.refresh_access_token(db, body.refresh_token)


@router.post("/logout")
def logout(
    body: LogoutRequest | None = None,
    user: User = Depends(get_current_user),
):
    if body and body.refresh_token:
        auth_service.blacklist_refresh_token(body.refresh_token)
    return {"message": "已退出登录"}


@router.get("/me")
def me(user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    return auth_service.get_me(db, user)


@router.patch("/profile")
def update_profile(
    body: ProfileUpdateRequest,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    return auth_service.update_profile(
        db,
        user,
        display_name=body.display_name,
        bio=body.bio,
        avatar_url=body.avatar_url,
        clear_avatar=body.avatar_url == "",
    )
