"""画布项目访问控制。"""

from __future__ import annotations

from fastapi import HTTPException
from sqlalchemy.orm import Session

from models import User
from models.canvas_project import CanvasProject, utcnow
from services.team_service import EDIT_ROLES, get_member_role, require_team_editor


def get_accessible_project(
    db: Session,
    user: User,
    project_id: str,
    *,
    require_edit: bool = False,
) -> CanvasProject:
    row = db.get(CanvasProject, project_id)
    if not row:
        raise HTTPException(status_code=404, detail="项目不存在")

    if row.team_id:
        role = get_member_role(db, row.team_id, user.id)
        if not role:
            raise HTTPException(status_code=403, detail="无权访问该团队项目")
        if require_edit and role not in EDIT_ROLES:
            raise HTTPException(status_code=403, detail="没有编辑权限")
        return row

    if row.user_id != user.id:
        raise HTTPException(status_code=404, detail="项目不存在")
    return row


def list_projects_query(db: Session, user: User, team_id: str | None):
    if team_id:
        role = get_member_role(db, team_id, user.id)
        if not role:
            raise HTTPException(status_code=403, detail="无权访问该团队")
        return (
            db.query(CanvasProject)
            .filter(CanvasProject.team_id == team_id)
            .order_by(CanvasProject.updated_at.desc())
        )
    return (
        db.query(CanvasProject)
        .filter(CanvasProject.user_id == user.id, CanvasProject.team_id.is_(None))
        .order_by(CanvasProject.updated_at.desc())
    )


def touch_project_updated_at(db: Session, project_id: str) -> None:
    """更新项目 updated_at，不递增 version（协作活动标记）。"""
    row = db.get(CanvasProject, project_id)
    if not row:
        return
    row.updated_at = utcnow()


def migrate_project_to_team(
    db: Session,
    user: User,
    project_id: str,
    team_id: str,
) -> CanvasProject:
    """将个人画布迁移到团队（仅创建者可操作，且须为团队编辑者）。"""
    row = db.get(CanvasProject, project_id)
    if not row:
        raise HTTPException(status_code=404, detail="项目不存在")
    if int(row.user_id) != int(user.id):
        raise HTTPException(status_code=403, detail="仅项目创建者可迁移到团队")
    if row.team_id:
        raise HTTPException(status_code=400, detail="该项目已是团队画布")
    require_team_editor(db, team_id, user)
    row.team_id = team_id
    row.updated_at = utcnow()
    db.commit()
    db.refresh(row)
    return row
