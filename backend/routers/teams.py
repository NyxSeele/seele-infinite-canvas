from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from core.dependencies import get_current_user
from db.session import get_db
from models import User
from models.team import Team, TeamMember
from schemas.team import (
    MemberQuotaUsage,
    TeamCreate,
    TeamInviteCreate,
    TeamInviteOut,
    TeamInvitePreview,
    TeamJoinRequest,
    TeamListResponse,
    TeamMemberAdd,
    TeamMemberOut,
    TeamMemberUpdate,
    TeamOut,
    TeamUpdate,
)
from services.quota_service import get_or_create_user_quota
from services.team_invite_service import (
    create_or_refresh_invite,
    invite_to_dict,
    join_team_by_invite,
    preview_invite,
)
from services import team_mine_cache
from services.team_service import (
    add_member_by_username,
    create_team,
    get_membership,
    list_user_teams,
    require_team_admin,
    require_team_member,
    team_to_dict,
)


def _member_out(db: Session, member: TeamMember, u: User) -> TeamMemberOut:
    quota = get_or_create_user_quota(db, member.user_id)
    return TeamMemberOut(
        user_id=member.user_id,
        username=u.username,
        email=u.email,
        role=member.role,
        joined_at=member.joined_at,
        quota_settings=member.quota_settings_dict(),
        quota=MemberQuotaUsage(
            image_limit=quota.image_limit,
            image_used=quota.image_used,
            video_limit=quota.video_limit,
            video_used=quota.video_used,
        ),
    )


def _build_mine_response(db: Session, user: User) -> TeamListResponse:
    owned, joined = list_user_teams(db, user)
    return TeamListResponse(
        owned=TeamOut(**team_to_dict(db, owned, user)) if owned else None,
        joined=[TeamOut(**team_to_dict(db, t, user)) for t in joined],
    )

router = APIRouter(prefix="/api/teams", tags=["teams"])


@router.get("/mine", response_model=TeamListResponse)
def get_my_teams(
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    cached = team_mine_cache.get_fresh(user.id)
    if cached is not None:
        return cached

    if not team_mine_cache.allow_db_hit(user.id):
        stale = team_mine_cache.get_stale(user.id)
        if stale is not None:
            return stale

    result = _build_mine_response(db, user)
    team_mine_cache.store(user.id, result)
    return result


@router.post("", response_model=TeamOut)
def create_my_team(
    body: TeamCreate,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    team = create_team(db, user, body.name)
    team_mine_cache.invalidate_user(user.id)
    return TeamOut(**team_to_dict(db, team, user))


def _invite_url(token: str) -> str:
    return f"/join-team?token={token}"


@router.get("/invites/{token}", response_model=TeamInvitePreview)
def preview_team_invite(
    token: str,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    data = preview_invite(db, token, user)
    return TeamInvitePreview(
        team=TeamOut(**data["team"]),
        settings=data.get("settings") or {},
        already_member=data.get("already_member", False),
        my_role=data.get("my_role"),
    )


@router.post("/join", response_model=TeamOut)
def join_team_with_invite(
    body: TeamJoinRequest,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    team = join_team_by_invite(db, body.token.strip(), user)
    team_mine_cache.invalidate_user(user.id)
    return TeamOut(**team)


@router.get("/{team_id}", response_model=TeamOut)
def get_team(
    team_id: str,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    require_team_member(db, team_id, user)
    team = db.get(Team, team_id)
    if not team:
        raise HTTPException(status_code=404, detail="团队不存在")
    return TeamOut(**team_to_dict(db, team, user))


@router.patch("/{team_id}", response_model=TeamOut)
def update_team(
    team_id: str,
    body: TeamUpdate,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    require_team_admin(db, team_id, user)
    team = db.get(Team, team_id)
    if not team:
        raise HTTPException(status_code=404, detail="团队不存在")
    if body.name is not None:
        team.name = body.name.strip()[:128] or team.name
    db.commit()
    db.refresh(team)
    team_mine_cache.invalidate_user(user.id)
    return TeamOut(**team_to_dict(db, team, user))


@router.get("/{team_id}/members", response_model=list[TeamMemberOut])
def list_members(
    team_id: str,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    require_team_member(db, team_id, user)
    rows = (
        db.query(TeamMember, User)
        .join(User, User.id == TeamMember.user_id)
        .filter(TeamMember.team_id == team_id)
        .order_by(TeamMember.joined_at.asc())
        .all()
    )
    return [_member_out(db, member, u) for member, u in rows]


@router.post("/{team_id}/members", response_model=TeamMemberOut)
def add_member(
    team_id: str,
    body: TeamMemberAdd,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    row = add_member_by_username(db, team_id, user, body.username, body.role)
    team_mine_cache.invalidate_users(user.id, row.user_id)
    target = db.get(User, row.user_id)
    if not target:
        raise HTTPException(status_code=404, detail="用户不存在")
    return _member_out(db, row, target)


@router.patch("/{team_id}/members/{member_user_id}", response_model=TeamMemberOut)
def update_member_role(
    team_id: str,
    member_user_id: int,
    body: TeamMemberUpdate,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    require_team_admin(db, team_id, user)
    row = get_membership(db, team_id, member_user_id)
    if not row:
        raise HTTPException(status_code=404, detail="成员不存在")
    if row.role == "owner":
        raise HTTPException(status_code=400, detail="不能修改所有者角色")
    if body.role == "owner":
        raise HTTPException(status_code=400, detail="不能设为所有者")
    row.role = body.role
    db.commit()
    db.refresh(row)
    team_mine_cache.invalidate_users(user.id, member_user_id)
    target = db.get(User, row.user_id)
    if not target:
        raise HTTPException(status_code=404, detail="用户不存在")
    return _member_out(db, row, target)


@router.delete("/{team_id}/members/{member_user_id}")
def remove_member(
    team_id: str,
    member_user_id: int,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    require_team_admin(db, team_id, user)
    row = get_membership(db, team_id, member_user_id)
    if not row:
        raise HTTPException(status_code=404, detail="成员不存在")
    if row.role == "owner":
        raise HTTPException(status_code=400, detail="不能移除所有者")
    db.delete(row)
    db.commit()
    team_mine_cache.invalidate_users(user.id, member_user_id)
    return {"ok": True}


@router.get("/{team_id}/invite-link", response_model=TeamInviteOut)
def get_team_invite_link(
    team_id: str,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    invite = create_or_refresh_invite(
        db, team_id=team_id, actor=user, settings=None, force_new=False
    )
    return TeamInviteOut(**invite_to_dict(invite, url=_invite_url(invite.token)))


@router.post("/{team_id}/invite-link", response_model=TeamInviteOut)
def create_team_invite_link(
    team_id: str,
    body: TeamInviteCreate | None = None,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    settings = body.settings.model_dump() if body and body.settings else None
    force_new = bool(body and body.settings)
    invite = create_or_refresh_invite(
        db,
        team_id=team_id,
        actor=user,
        settings=settings,
        force_new=force_new,
    )
    team_mine_cache.invalidate_user(user.id)
    return TeamInviteOut(**invite_to_dict(invite, url=_invite_url(invite.token)))


@router.post("/{team_id}/leave")
def leave_team(
    team_id: str,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    row = get_membership(db, team_id, user.id)
    if not row:
        raise HTTPException(status_code=404, detail="你不在该团队中")
    if row.role == "owner":
        raise HTTPException(status_code=400, detail="所有者不能退出，请转让或解散团队")
    db.delete(row)
    db.commit()
    team_mine_cache.invalidate_user(user.id)
    return {"ok": True}
