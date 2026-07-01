"""团队权限与成员管理。"""

from __future__ import annotations

from fastapi import HTTPException
from sqlalchemy.orm import Session

from models import User
from models.team import Team, TeamMember, new_team_id

EDIT_ROLES = frozenset({"owner", "admin", "editor"})
ADMIN_ROLES = frozenset({"owner", "admin"})
ALL_ROLES = frozenset({"owner", "admin", "editor", "viewer"})


def get_owned_team(db: Session, user_id: int) -> Team | None:
    return db.query(Team).filter(Team.owner_id == user_id).first()


def get_membership(db: Session, team_id: str, user_id: int) -> TeamMember | None:
    return (
        db.query(TeamMember)
        .filter(TeamMember.team_id == team_id, TeamMember.user_id == user_id)
        .first()
    )


def get_member_role(db: Session, team_id: str | None, user_id: int) -> str | None:
    if not team_id:
        return None
    row = get_membership(db, team_id, user_id)
    return row.role if row else None


def require_team_member(db: Session, team_id: str, user: User) -> TeamMember:
    team = db.get(Team, team_id)
    if not team:
        raise HTTPException(status_code=404, detail="团队不存在")
    member = get_membership(db, team_id, user.id)
    if not member:
        raise HTTPException(status_code=403, detail="你不是该团队成员")
    return member


def require_team_editor(db: Session, team_id: str, user: User) -> TeamMember:
    member = require_team_member(db, team_id, user)
    if member.role not in EDIT_ROLES:
        raise HTTPException(status_code=403, detail="没有编辑权限")
    return member


def require_team_admin(db: Session, team_id: str, user: User) -> TeamMember:
    member = require_team_member(db, team_id, user)
    if member.role not in ADMIN_ROLES:
        raise HTTPException(status_code=403, detail="没有管理权限")
    return member


def create_team(db: Session, user: User, name: str) -> Team:
    if get_owned_team(db, user.id):
        raise HTTPException(status_code=400, detail="每个账号只能创建一个团队")
    trimmed = (name or "").strip()[:128]
    if not trimmed:
        raise HTTPException(status_code=400, detail="团队名称不能为空")
    team = Team(id=new_team_id(), name=trimmed, owner_id=user.id)
    db.add(team)
    db.flush()
    db.add(TeamMember(team_id=team.id, user_id=user.id, role="owner"))
    db.commit()
    db.refresh(team)
    return team


def add_member_by_username(
    db: Session,
    team_id: str,
    actor: User,
    username: str,
    role: str = "editor",
) -> TeamMember:
    require_team_admin(db, team_id, actor)
    if role not in ALL_ROLES or role == "owner":
        raise HTTPException(status_code=400, detail="无效角色")
    target = db.query(User).filter(User.username == username.strip()).first()
    if not target:
        raise HTTPException(status_code=404, detail="用户不存在")
    existing = get_membership(db, team_id, target.id)
    if existing:
        raise HTTPException(status_code=400, detail="用户已在团队中")
    if get_membership(db, team_id, actor.id) is None:
        raise HTTPException(status_code=403, detail="无权操作")
    row = TeamMember(team_id=team_id, user_id=target.id, role=role)
    db.add(row)
    db.commit()
    db.refresh(row)
    return row


def list_user_teams(db: Session, user: User) -> tuple[Team | None, list[Team]]:
    owned = get_owned_team(db, user.id)
    joined_ids = (
        db.query(TeamMember.team_id)
        .filter(TeamMember.user_id == user.id, TeamMember.role != "owner")
        .all()
    )
    ids = [r[0] for r in joined_ids]
    joined = db.query(Team).filter(Team.id.in_(ids)).order_by(Team.created_at.desc()).all() if ids else []
    return owned, joined


def team_to_dict(db: Session, team: Team, user: User) -> dict:
    member = get_membership(db, team.id, user.id)
    owner = db.get(User, team.owner_id)
    count = db.query(TeamMember).filter(TeamMember.team_id == team.id).count()
    return {
        "id": team.id,
        "name": team.name,
        "owner_id": team.owner_id,
        "owner_username": owner.username if owner else None,
        "my_role": member.role if member else "viewer",
        "created_at": team.created_at,
        "member_count": count,
    }
