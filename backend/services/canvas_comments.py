"""画布卡片评论（按 node_id 线程）。"""

from __future__ import annotations

import json
from datetime import datetime, timezone

from fastapi import HTTPException
from sqlalchemy.orm import Session

from core.datetime_utils import to_utc_iso
from models.canvas_comment import CanvasCommentMessage, CanvasCommentThread, new_comment_id
from models.canvas_project import CanvasProject
from services.canvas_access import touch_project_updated_at
from services.notification_service import create_comment_mention_notifications
from services.user_profile import avatar_url_map
from services.canvas_lock import publish_project_event

MAX_BODY_LEN = 200


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _parse_mentioned_ids(raw: list[int] | None) -> list[int]:
    out: list[int] = []
    seen: set[int] = set()
    for item in raw or []:
        try:
            uid = int(item)
        except (TypeError, ValueError):
            continue
        if uid in seen:
            continue
        seen.add(uid)
        out.append(uid)
    return out


def _mentioned_ids_from_row(row: CanvasCommentMessage) -> list[int]:
    if not row.mentioned_user_ids:
        return []
    try:
        data = json.loads(row.mentioned_user_ids)
        if isinstance(data, list):
            return _parse_mentioned_ids(data)
    except (json.JSONDecodeError, TypeError):
        pass
    return []


def _serialize_message(row: CanvasCommentMessage, avatars: dict[int, str] | None = None) -> dict:
    avatars = avatars or {}
    return {
        "id": row.id,
        "thread_id": row.thread_id,
        "author_id": row.author_id,
        "author_name": row.author_name,
        "author_avatar_url": avatars.get(int(row.author_id), ""),
        "body": row.body,
        "mentioned_user_ids": _mentioned_ids_from_row(row),
        "created_at": to_utc_iso(row.created_at),
        "updated_at": to_utc_iso(row.updated_at),
    }


def _serialize_thread(
    thread: CanvasCommentThread,
    messages: list[CanvasCommentMessage],
    avatars: dict[int, str] | None = None,
) -> dict:
    return {
        "id": thread.id,
        "project_id": thread.project_id,
        "node_id": thread.node_id,
        "created_by": thread.created_by,
        "created_at": to_utc_iso(thread.created_at),
        "messages": [_serialize_message(m, avatars) for m in messages],
    }


def _thread_payload(
    db: Session,
    thread: CanvasCommentThread,
    messages: list[CanvasCommentMessage],
) -> dict:
    author_ids = {int(m.author_id) for m in messages}
    avatars = avatar_url_map(db, author_ids)
    return _serialize_thread(thread, messages, avatars)


def list_project_comments(db: Session, project_id: str) -> list[dict]:
    threads = (
        db.query(CanvasCommentThread)
        .filter(CanvasCommentThread.project_id == project_id)
        .order_by(CanvasCommentThread.created_at.asc())
        .all()
    )
    if not threads:
        return []
    thread_ids = [t.id for t in threads]
    messages = (
        db.query(CanvasCommentMessage)
        .filter(CanvasCommentMessage.thread_id.in_(thread_ids))
        .order_by(CanvasCommentMessage.created_at.asc())
        .all()
    )
    by_thread: dict[str, list[CanvasCommentMessage]] = {}
    for m in messages:
        by_thread.setdefault(m.thread_id, []).append(m)
    author_ids = {int(m.author_id) for m in messages}
    avatars = avatar_url_map(db, author_ids)
    return [_serialize_thread(t, by_thread.get(t.id, []), avatars) for t in threads]


def get_or_create_thread(db: Session, project_id: str, node_id: str, user_id: int) -> CanvasCommentThread:
    thread = (
        db.query(CanvasCommentThread)
        .filter(
            CanvasCommentThread.project_id == project_id,
            CanvasCommentThread.node_id == node_id,
        )
        .first()
    )
    if thread:
        return thread
    thread = CanvasCommentThread(
        id=new_comment_id(),
        project_id=project_id,
        node_id=node_id,
        created_by=user_id,
        created_at=_utcnow(),
    )
    db.add(thread)
    db.flush()
    return thread


def _publish_comment_event(project_id: str, event_type: str, payload: dict) -> None:
    publish_project_event(project_id, {"type": event_type, **payload})


def _notify_mentions(
    db: Session,
    *,
    project_id: str,
    node_id: str,
    message: CanvasCommentMessage,
    author_name: str,
    mentioned_user_ids: list[int],
) -> None:
    if not mentioned_user_ids:
        return
    project = db.query(CanvasProject).filter(CanvasProject.id == project_id).first()
    project_name = project.name if project else ""
    created = create_comment_mention_notifications(
        db,
        mentioned_user_ids=mentioned_user_ids,
        author_id=message.author_id,
        author_name=author_name,
        project_id=project_id,
        project_name=project_name,
        node_id=node_id,
        comment_id=message.id,
        body_preview=message.body,
    )
    for recipient_id, note in created:
        payload = note.get("payload") or {}
        publish_project_event(
            project_id,
            {
                "type": "comment_mention",
                "project_id": project_id,
                "recipient_user_id": recipient_id,
                "mentioner": payload.get("mentioner"),
                "node_id": node_id,
                "comment_id": message.id,
                "body_preview": payload.get("body_preview"),
                "notification_id": note.get("id"),
            },
        )


def add_comment(
    db: Session,
    *,
    project_id: str,
    node_id: str,
    body: str,
    user_id: int,
    username: str,
    mentioned_user_ids: list[int] | None = None,
) -> dict:
    text = (body or "").strip()
    if not text:
        raise HTTPException(status_code=400, detail="评论内容不能为空")
    if len(text) > MAX_BODY_LEN:
        raise HTTPException(status_code=400, detail=f"评论最多 {MAX_BODY_LEN} 字")

    mentions = _parse_mentioned_ids(mentioned_user_ids)
    thread = get_or_create_thread(db, project_id, node_id, user_id)
    msg = CanvasCommentMessage(
        id=new_comment_id(),
        thread_id=thread.id,
        author_id=user_id,
        author_name=username or str(user_id),
        body=text,
        mentioned_user_ids=json.dumps(mentions) if mentions else None,
        created_at=_utcnow(),
    )
    db.add(msg)
    db.flush()
    _notify_mentions(
        db,
        project_id=project_id,
        node_id=node_id,
        message=msg,
        author_name=username or str(user_id),
        mentioned_user_ids=mentions,
    )
    touch_project_updated_at(db, project_id)
    db.commit()
    db.refresh(msg)
    db.refresh(thread)

    messages = (
        db.query(CanvasCommentMessage)
        .filter(CanvasCommentMessage.thread_id == thread.id)
        .order_by(CanvasCommentMessage.created_at.asc())
        .all()
    )
    thread_data = _thread_payload(db, thread, messages)
    _publish_comment_event(
        project_id,
        "comment_updated",
        {"project_id": project_id, "thread": thread_data},
    )
    return thread_data


def reply_comment(
    db: Session,
    *,
    project_id: str,
    thread_id: str,
    body: str,
    user_id: int,
    username: str,
    mentioned_user_ids: list[int] | None = None,
) -> dict:
    thread = (
        db.query(CanvasCommentThread)
        .filter(
            CanvasCommentThread.id == thread_id,
            CanvasCommentThread.project_id == project_id,
        )
        .first()
    )
    if not thread:
        raise HTTPException(status_code=404, detail="评论线程不存在")

    text = (body or "").strip()
    if not text:
        raise HTTPException(status_code=400, detail="回复内容不能为空")
    if len(text) > MAX_BODY_LEN:
        raise HTTPException(status_code=400, detail=f"回复最多 {MAX_BODY_LEN} 字")

    mentions = _parse_mentioned_ids(mentioned_user_ids)
    msg = CanvasCommentMessage(
        id=new_comment_id(),
        thread_id=thread.id,
        author_id=user_id,
        author_name=username or str(user_id),
        body=text,
        mentioned_user_ids=json.dumps(mentions) if mentions else None,
        created_at=_utcnow(),
    )
    db.add(msg)
    db.flush()
    _notify_mentions(
        db,
        project_id=project_id,
        node_id=thread.node_id,
        message=msg,
        author_name=username or str(user_id),
        mentioned_user_ids=mentions,
    )
    touch_project_updated_at(db, project_id)
    db.commit()

    messages = (
        db.query(CanvasCommentMessage)
        .filter(CanvasCommentMessage.thread_id == thread.id)
        .order_by(CanvasCommentMessage.created_at.asc())
        .all()
    )
    thread_data = _thread_payload(db, thread, messages)
    _publish_comment_event(
        project_id,
        "comment_updated",
        {"project_id": project_id, "thread": thread_data},
    )
    return thread_data


def update_message(
    db: Session,
    *,
    project_id: str,
    message_id: str,
    body: str,
    user_id: int,
) -> dict:
    msg = (
        db.query(CanvasCommentMessage)
        .join(CanvasCommentThread, CanvasCommentThread.id == CanvasCommentMessage.thread_id)
        .filter(
            CanvasCommentMessage.id == message_id,
            CanvasCommentThread.project_id == project_id,
        )
        .first()
    )
    if not msg:
        raise HTTPException(status_code=404, detail="评论不存在")
    if int(msg.author_id) != int(user_id):
        raise HTTPException(status_code=403, detail="只能编辑自己的评论")

    text = (body or "").strip()
    if not text:
        raise HTTPException(status_code=400, detail="评论内容不能为空")
    if len(text) > MAX_BODY_LEN:
        raise HTTPException(status_code=400, detail=f"评论最多 {MAX_BODY_LEN} 字")

    msg.body = text
    msg.updated_at = _utcnow()
    touch_project_updated_at(db, project_id)
    db.commit()

    thread = db.query(CanvasCommentThread).filter(CanvasCommentThread.id == msg.thread_id).first()
    messages = (
        db.query(CanvasCommentMessage)
        .filter(CanvasCommentMessage.thread_id == msg.thread_id)
        .order_by(CanvasCommentMessage.created_at.asc())
        .all()
    )
    thread_data = _thread_payload(db, thread, messages)
    _publish_comment_event(
        project_id,
        "comment_updated",
        {"project_id": project_id, "thread": thread_data},
    )
    return thread_data


def delete_message(
    db: Session,
    *,
    project_id: str,
    message_id: str,
    user_id: int,
) -> dict | None:
    msg = (
        db.query(CanvasCommentMessage)
        .join(CanvasCommentThread, CanvasCommentThread.id == CanvasCommentMessage.thread_id)
        .filter(
            CanvasCommentMessage.id == message_id,
            CanvasCommentThread.project_id == project_id,
        )
        .first()
    )
    if not msg:
        raise HTTPException(status_code=404, detail="评论不存在")
    if int(msg.author_id) != int(user_id):
        raise HTTPException(status_code=403, detail="只能删除自己的评论")

    thread_id = msg.thread_id
    thread = db.query(CanvasCommentThread).filter(CanvasCommentThread.id == thread_id).first()
    node_id = thread.node_id if thread else None
    db.delete(msg)
    db.flush()

    remaining = (
        db.query(CanvasCommentMessage)
        .filter(CanvasCommentMessage.thread_id == thread_id)
        .count()
    )
    if remaining == 0 and thread:
        db.delete(thread)
        touch_project_updated_at(db, project_id)
        db.commit()
        _publish_comment_event(
            project_id,
            "comment_deleted",
            {"project_id": project_id, "node_id": node_id, "thread_id": thread_id},
        )
        return {"deleted": True, "node_id": node_id, "thread_id": thread_id}

    touch_project_updated_at(db, project_id)
    db.commit()
    messages = (
        db.query(CanvasCommentMessage)
        .filter(CanvasCommentMessage.thread_id == thread_id)
        .order_by(CanvasCommentMessage.created_at.asc())
        .all()
    )
    thread_data = _thread_payload(db, thread, messages)
    _publish_comment_event(
        project_id,
        "comment_updated",
        {"project_id": project_id, "thread": thread_data},
    )
    return thread_data
