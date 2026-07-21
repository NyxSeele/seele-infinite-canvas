"""项目最近协作者持久化。"""

from __future__ import annotations

import time
from datetime import datetime, timezone

from sqlalchemy import func
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.dialects.sqlite import insert as sqlite_insert
from sqlalchemy.orm import Session

from db.session import SessionLocal
from models import User
from models.project_collaborator import ProjectCollaborator

_THROTTLE: dict[tuple[str, int], float] = {}
THROTTLE_SEC = 30


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def touch_collaborator(db: Session, project_id: str, user_id: int) -> None:
    now = _utcnow()
    bind = db.get_bind()
    dialect = bind.dialect.name if bind is not None else ""
    if dialect == "postgresql":
        stmt = pg_insert(ProjectCollaborator).values(
            project_id=project_id,
            user_id=user_id,
            last_active_at=now,
        )
        stmt = stmt.on_conflict_do_update(
            index_elements=["project_id", "user_id"],
            set_={"last_active_at": now},
        )
        db.execute(stmt)
        return

    if dialect == "sqlite":
        stmt = sqlite_insert(ProjectCollaborator).values(
            project_id=project_id,
            user_id=user_id,
            last_active_at=now,
        )
        stmt = stmt.on_conflict_do_update(
            index_elements=["project_id", "user_id"],
            set_={"last_active_at": now},
        )
        db.execute(stmt)
        return

    row = (
        db.query(ProjectCollaborator)
        .filter(
            ProjectCollaborator.project_id == project_id,
            ProjectCollaborator.user_id == user_id,
        )
        .first()
    )
    if row:
        row.last_active_at = now
    else:
        db.add(
            ProjectCollaborator(
                project_id=project_id,
                user_id=user_id,
                last_active_at=now,
            )
        )


def touch_collaborator_throttled(
    project_id: str,
    user_id: int,
    *,
    force: bool = False,
) -> None:
    key = (project_id, int(user_id))
    now = time.time()
    if not force and key in _THROTTLE and now - _THROTTLE[key] < THROTTLE_SEC:
        return
    _THROTTLE[key] = now
    db = SessionLocal()
    try:
        touch_collaborator(db, project_id, int(user_id))
        db.commit()
    finally:
        db.close()


def _collaborator_payload(user: User, last_active_at: datetime) -> dict:
    label = (user.display_name or "").strip() or user.username or str(user.id)
    return {
        "user_id": int(user.id),
        "display_name": label,
        "avatar_url": (user.avatar_url or "").strip(),
        "last_active_at": last_active_at.isoformat(),
    }


def list_recent_collaborators_batch(
    db: Session,
    project_ids: list[str],
    *,
    limit: int = 3,
) -> dict[str, dict]:
    if not project_ids:
        return {}

    rows = (
        db.query(ProjectCollaborator, User)
        .join(User, User.id == ProjectCollaborator.user_id)
        .filter(ProjectCollaborator.project_id.in_(project_ids))
        .order_by(
            ProjectCollaborator.project_id.asc(),
            ProjectCollaborator.last_active_at.desc(),
        )
        .all()
    )

    grouped: dict[str, list[dict]] = {}
    counts: dict[str, int] = {}
    for collab, user in rows:
        pid = collab.project_id
        counts[pid] = counts.get(pid, 0) + 1
        bucket = grouped.setdefault(pid, [])
        if len(bucket) < limit:
            bucket.append(_collaborator_payload(user, collab.last_active_at))

    out: dict[str, dict] = {}
    for pid in project_ids:
        total = counts.get(pid, 0)
        recent = grouped.get(pid, [])
        out[pid] = {
            "recent_collaborators": recent,
            "collaborator_extra_count": max(0, total - len(recent)),
        }
    return out


def list_recent_collaborators_for_project(
    db: Session,
    project_id: str,
    *,
    limit: int = 3,
) -> dict:
    return list_recent_collaborators_batch(db, [project_id], limit=limit).get(
        project_id,
        {"recent_collaborators": [], "collaborator_extra_count": 0},
    )
