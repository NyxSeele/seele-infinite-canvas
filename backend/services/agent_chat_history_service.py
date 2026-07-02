import json
import uuid
from datetime import datetime, timezone

from sqlalchemy.orm import Session

from core.datetime_utils import to_utc_iso
from models.agent_chat_archive import AgentChatArchive
from services.canvas_access import touch_project_updated_at

MAX_ARCHIVES_PER_PROJECT = 30
MAX_MESSAGES_PER_ARCHIVE = 80


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _title_from_messages(messages: list[dict]) -> str:
    first_user = next((m for m in messages if m.get("role") == "user"), None)
    text = (first_user.get("content") or "").strip() if first_user else ""
    if not text:
        return "未命名对话"
    return text[:28] + "…" if len(text) > 28 else text


def list_chat_archives(db: Session, user_id: int, project_id: str) -> list[dict]:
    rows = (
        db.query(AgentChatArchive)
        .filter(
            AgentChatArchive.user_id == user_id,
            AgentChatArchive.project_id == project_id,
        )
        .order_by(AgentChatArchive.updated_at.desc())
        .limit(MAX_ARCHIVES_PER_PROJECT)
        .all()
    )
    result = []
    for row in rows:
        try:
            msgs = json.loads(row.messages)
            count = len(msgs) if isinstance(msgs, list) else 0
        except json.JSONDecodeError:
            count = 0
            msgs = []
        result.append(
            {
                "id": row.id,
                "project_id": row.project_id,
                "title": row.title,
                "messages": msgs if isinstance(msgs, list) else [],
                "updated_at": to_utc_iso(row.updated_at),
                "updatedAt": int(row.updated_at.timestamp() * 1000) if row.updated_at else 0,
                "message_count": count,
            }
        )
    return result


def save_chat_archive(
    db: Session,
    user_id: int,
    project_id: str,
    messages: list[dict],
    *,
    archive_id: str | None = None,
    title: str | None = None,
) -> dict:
    if not messages:
        raise ValueError("messages 不能为空")
    if len(messages) > MAX_MESSAGES_PER_ARCHIVE:
        messages = messages[-MAX_MESSAGES_PER_ARCHIVE:]

    entry_id = archive_id or str(uuid.uuid4())
    entry_title = (title or "").strip() or _title_from_messages(messages)
    payload = json.dumps(messages, ensure_ascii=False)
    now = _utcnow()

    row = (
        db.query(AgentChatArchive)
        .filter(
            AgentChatArchive.id == entry_id,
            AgentChatArchive.user_id == user_id,
            AgentChatArchive.project_id == project_id,
        )
        .first()
    )
    if row:
        row.title = entry_title
        row.messages = payload
        row.updated_at = now
    else:
        row = AgentChatArchive(
            id=entry_id,
            project_id=project_id,
            user_id=user_id,
            title=entry_title,
            messages=payload,
            created_at=now,
            updated_at=now,
        )
        db.add(row)

    touch_project_updated_at(db, project_id)
    db.commit()

    total = (
        db.query(AgentChatArchive)
        .filter(
            AgentChatArchive.user_id == user_id,
            AgentChatArchive.project_id == project_id,
        )
        .order_by(AgentChatArchive.updated_at.desc())
        .all()
    )
    if len(total) > MAX_ARCHIVES_PER_PROJECT:
        for stale in total[MAX_ARCHIVES_PER_PROJECT:]:
            db.delete(stale)
        db.commit()

    return {
        "id": entry_id,
        "project_id": project_id,
        "title": entry_title,
        "messages": messages,
        "updatedAt": int(now.timestamp() * 1000),
    }


def delete_chat_archive(
    db: Session, user_id: int, project_id: str, archive_id: str
) -> bool:
    row = (
        db.query(AgentChatArchive)
        .filter(
            AgentChatArchive.id == archive_id,
            AgentChatArchive.user_id == user_id,
            AgentChatArchive.project_id == project_id,
        )
        .first()
    )
    if not row:
        return False
    db.delete(row)
    touch_project_updated_at(db, project_id)
    db.commit()
    return True
