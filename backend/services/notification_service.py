"""用户通知（评论 @ 提及等）。"""

from __future__ import annotations

import json
from datetime import datetime, timezone

from sqlalchemy.orm import Session

from core.datetime_utils import to_utc_iso
from models.notification import Notification, new_notification_id


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _serialize(row: Notification) -> dict:
    return {
        "id": row.id,
        "type": row.type,
        "payload": row.payload_dict(),
        "is_read": row.is_read,
        "created_at": to_utc_iso(row.created_at),
    }


def create_comment_mention_notifications(
    db: Session,
    *,
    mentioned_user_ids: list[int],
    author_id: int,
    author_name: str,
    project_id: str,
    project_name: str | None,
    node_id: str,
    comment_id: str,
    body_preview: str,
) -> list[tuple[int, dict]]:
    created: list[tuple[int, dict]] = []
    seen: set[int] = set()
    for raw_id in mentioned_user_ids or []:
        try:
            uid = int(raw_id)
        except (TypeError, ValueError):
            continue
        if uid == int(author_id) or uid in seen:
            continue
        seen.add(uid)
        payload = {
            "project_id": project_id,
            "project_name": project_name or "",
            "node_id": node_id,
            "comment_id": comment_id,
            "mentioner": {
                "user_id": author_id,
                "name": author_name,
            },
            "body_preview": (body_preview or "")[:120],
        }
        row = Notification(
            id=new_notification_id(),
            user_id=uid,
            type="comment_mention",
            payload=json.dumps(payload, ensure_ascii=False),
            is_read=False,
            created_at=_utcnow(),
        )
        db.add(row)
        created.append((uid, _serialize(row)))
    if created:
        db.flush()
    return created


def list_notifications(
    db: Session,
    user_id: int,
    *,
    limit: int = 50,
    offset: int = 0,
) -> dict:
    q = (
        db.query(Notification)
        .filter(Notification.user_id == user_id)
        .order_by(Notification.created_at.desc())
    )
    total = q.count()
    unread = (
        db.query(Notification)
        .filter(Notification.user_id == user_id, Notification.is_read.is_(False))
        .count()
    )
    rows = q.offset(max(0, offset)).limit(min(100, max(1, limit))).all()
    return {
        "notifications": [_serialize(r) for r in rows],
        "total": total,
        "unread_count": unread,
    }


def mark_notifications_read(
    db: Session,
    user_id: int,
    *,
    notification_ids: list[str] | None = None,
    mark_all: bool = False,
) -> int:
    q = db.query(Notification).filter(
        Notification.user_id == user_id,
        Notification.is_read.is_(False),
    )
    if not mark_all:
        ids = [i for i in (notification_ids or []) if i]
        if not ids:
            return 0
        q = q.filter(Notification.id.in_(ids))
    updated = q.update({Notification.is_read: True}, synchronize_session=False)
    db.commit()
    return int(updated or 0)
