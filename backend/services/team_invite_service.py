"""团队邀请链接。"""

from __future__ import annotations

import json
from datetime import timedelta

from fastapi import HTTPException
from sqlalchemy.orm import Session

from models import User
from models.team import Team
from models.team_invite import TeamInvite, new_invite_token, utcnow
from services.quota_service import get_or_create_user_quota
from services.team_service import get_membership, require_team_admin, team_to_dict

DEFAULT_SETTINGS = {
    "expiryDays": 7,
    "maxUses": 0,
    "quotaType": "unlimited",
    "periodicCycle": "monthly",
    "periodicAmount": 20000,
    "fixedAmount": 20000,
}


def _expiry_from_days(days: int):
    if days <= 0:
        return None
    return utcnow() + timedelta(days=days)


def invite_to_dict(invite: TeamInvite, *, url: str) -> dict:
    return {
        "token": invite.token,
        "team_id": invite.team_id,
        "url": url,
        "expires_at": invite.expires_at,
        "max_uses": invite.max_uses,
        "use_count": invite.use_count,
        "settings": invite.settings(),
        "created_at": invite.created_at,
    }


def _latest_invite(db: Session, team_id: str) -> TeamInvite | None:
    return (
        db.query(TeamInvite)
        .filter(TeamInvite.team_id == team_id)
        .order_by(TeamInvite.created_at.desc())
        .first()
    )


def create_or_refresh_invite(
    db: Session,
    *,
    team_id: str,
    actor: User,
    settings: dict | None = None,
    force_new: bool = False,
) -> TeamInvite:
    require_team_admin(db, team_id, actor)
    if not force_new and settings is None:
        existing = _latest_invite(db, team_id)
        if existing and not existing.is_expired() and not existing.is_exhausted():
            return existing

    merged = {**DEFAULT_SETTINGS, **(settings or {})}
    if not force_new and settings is None and (existing := _latest_invite(db, team_id)):
        merged = {**DEFAULT_SETTINGS, **existing.settings()}

    expiry_days = int(merged.get("expiryDays") or 0)
    max_uses = int(merged.get("maxUses") or 0)

    invite = TeamInvite(
        token=new_invite_token(),
        team_id=team_id,
        created_by=actor.id,
        expires_at=_expiry_from_days(expiry_days),
        max_uses=max(0, max_uses),
        use_count=0,
    )
    invite.set_settings(merged)
    db.add(invite)
    db.commit()
    db.refresh(invite)
    return invite


def get_invite(db: Session, token: str) -> TeamInvite | None:
    if not token:
        return None
    return db.get(TeamInvite, token.strip())


def validate_invite(db: Session, token: str) -> TeamInvite:
    invite = get_invite(db, token)
    if not invite:
        raise HTTPException(status_code=404, detail="邀请链接无效或已失效")
    if invite.is_expired():
        raise HTTPException(status_code=410, detail="邀请链接已过期")
    if invite.is_exhausted():
        raise HTTPException(status_code=410, detail="邀请链接已达使用上限")
    team = db.get(Team, invite.team_id)
    if not team:
        raise HTTPException(status_code=404, detail="团队不存在")
    return invite


def _apply_invite_quota(db: Session, user_id: int, settings: dict) -> None:
    """将邀请链接中的额度设置写入用户配额。"""
    quota_type = str(settings.get("quotaType") or "unlimited")
    quota = get_or_create_user_quota(db, user_id)
    if quota_type == "unlimited":
        quota.image_limit = -1
        quota.video_limit = -1
    elif quota_type == "fixed":
        amt = max(0, int(settings.get("fixedAmount") or 0))
        quota.image_limit = amt
        quota.video_limit = amt
    elif quota_type == "periodic":
        amt = max(0, int(settings.get("periodicAmount") or 0))
        quota.image_limit = amt
        quota.video_limit = amt
    db.flush()


def preview_invite(db: Session, token: str, user: User) -> dict:
    invite = validate_invite(db, token)
    team = db.get(Team, invite.team_id)
    existing = get_membership(db, invite.team_id, user.id)
    return {
        "team": team_to_dict(db, team, user),
        "settings": invite.settings(),
        "already_member": existing is not None,
        "my_role": existing.role if existing else None,
    }


def join_team_by_invite(db: Session, token: str, user: User):
    from models.team import TeamMember
    from services import team_mine_cache

    invite = validate_invite(db, token)
    team = db.get(Team, invite.team_id)
    if not team:
        raise HTTPException(status_code=404, detail="团队不存在")

    existing = get_membership(db, invite.team_id, user.id)
    if existing:
        return team_to_dict(db, team, user)

    if team.owner_id == user.id:
        raise HTTPException(status_code=400, detail="你是该团队所有者，无需加入")

    owned = (
        db.query(Team)
        .filter(Team.owner_id == user.id)
        .first()
    )
    if owned and owned.id != invite.team_id:
        pass

    invite_settings = invite.settings()
    row = TeamMember(
        team_id=invite.team_id,
        user_id=user.id,
        role="editor",
        quota_settings=json.dumps(invite_settings, ensure_ascii=False),
    )
    db.add(row)
    _apply_invite_quota(db, user.id, invite_settings)
    invite.use_count = int(invite.use_count or 0) + 1
    db.commit()
    db.refresh(row)
    team_mine_cache.invalidate_user(user.id)
    return team_to_dict(db, team, user)
