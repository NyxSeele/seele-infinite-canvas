"""用户资料字段（presence / 评论展示）。"""

from __future__ import annotations

from db.session import SessionLocal
from models import User


def presence_meta_for_user(user: User | None) -> tuple[str, str, str]:
    if not user:
        return "", "", ""
    label = (user.display_name or "").strip() or user.username or str(user.id)
    return (user.avatar_url or "").strip(), label, (user.email or "").strip()


def presence_meta_for_user_id(user_id: int) -> tuple[str, str, str]:
    db = SessionLocal()
    try:
        user = db.get(User, user_id)
        return presence_meta_for_user(user)
    finally:
        db.close()


def enrich_presence_members(members: list[dict]) -> list[dict]:
    if not members:
        return members
    ids = {int(m["user_id"]) for m in members if m.get("user_id") is not None}
    if not ids:
        return members
    db = SessionLocal()
    try:
        rows = db.query(User.id, User.email).filter(User.id.in_(ids)).all()
        emap = {int(r[0]): (r[1] or "").strip() for r in rows}
    finally:
        db.close()
    for m in members:
        uid = m.get("user_id")
        if uid is None:
            continue
        if not m.get("email"):
            m["email"] = emap.get(int(uid), "")
    return members


def avatar_url_map(db, user_ids: set[int]) -> dict[int, str]:
    if not user_ids:
        return {}
    rows = db.query(User.id, User.avatar_url).filter(User.id.in_(user_ids)).all()
    return {int(r[0]): (r[1] or "") for r in rows}
