import json
from datetime import datetime, timezone

from sqlalchemy.orm import Session

from models.agent_conversation import AgentConversation
from services.canvas_access import touch_project_updated_at

MAX_STORED_MESSAGES = 80


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def get_conversation_messages(
    db: Session, user_id: int, project_id: str
) -> list[dict]:
    row = (
        db.query(AgentConversation)
        .filter(
            AgentConversation.user_id == user_id,
            AgentConversation.project_id == project_id,
        )
        .first()
    )
    if not row or not row.messages:
        return []
    try:
        data = json.loads(row.messages)
        return data if isinstance(data, list) else []
    except json.JSONDecodeError:
        return []


def save_conversation_messages(
    db: Session, user_id: int, project_id: str, messages: list[dict]
) -> None:
    if len(messages) > MAX_STORED_MESSAGES:
        messages = messages[-MAX_STORED_MESSAGES:]
    payload = json.dumps(messages, ensure_ascii=False)
    row = (
        db.query(AgentConversation)
        .filter(
            AgentConversation.user_id == user_id,
            AgentConversation.project_id == project_id,
        )
        .first()
    )
    now = _utcnow()
    if row:
        row.messages = payload
        row.updated_at = now
    else:
        db.add(
            AgentConversation(
                project_id=project_id,
                user_id=user_id,
                messages=payload,
                created_at=now,
                updated_at=now,
            )
        )
    touch_project_updated_at(db, project_id)
    db.commit()
