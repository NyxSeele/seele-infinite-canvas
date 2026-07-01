"""画布 WebSocket 客户端消息处理。"""

from __future__ import annotations

from models import User
from services.canvas_lock import (
    create_edit_request,
    get_lock,
    get_pending_edit_request,
    publish_project_event,
    respond_edit_request,
)
from services.user_profile import presence_meta_for_user_id


def handle_client_message(project_id: str, user: User, msg: dict) -> None:
    msg_type = msg.get("type")
    if msg_type == "edit_request":
        _handle_edit_request(project_id, user, msg)
    elif msg_type == "edit_request_response":
        _handle_edit_request_response(project_id, user, msg)


def _handle_edit_request(project_id: str, user: User, msg: dict) -> None:
    lock = get_lock(project_id)
    if not lock:
        publish_project_event(
            project_id,
            {
                "type": "edit_request_response",
                "project_id": project_id,
                "status": "error",
                "message": "当前无人持有编辑锁",
                "requester": {"user_id": user.id},
            },
        )
        return
    if int(lock.get("user_id", -1)) == int(user.id):
        return
    try:
        _, label, _ = presence_meta_for_user_id(user.id)
        create_edit_request(
            project_id,
            requester_id=user.id,
            requester_username=user.username or str(user.id),
            requester_display_name=label,
        )
    except ValueError as exc:
        publish_project_event(
            project_id,
            {
                "type": "edit_request_response",
                "project_id": project_id,
                "status": "error",
                "message": str(exc),
                "requester": {"user_id": user.id},
            },
        )


def _handle_edit_request_response(project_id: str, user: User, msg: dict) -> None:
    request_id = str(msg.get("request_id") or "").strip()
    if not request_id:
        return
    approved = bool(msg.get("approved"))
    session_id = str(msg.get("session_id") or "").strip()
    if not session_id:
        return
    pending = get_pending_edit_request(project_id)
    if not pending:
        publish_project_event(
            project_id,
            {
                "type": "edit_request_response",
                "project_id": project_id,
                "status": "timeout",
                "request_id": request_id,
                "requester": msg.get("requester") or {},
            },
        )
        return
    try:
        respond_edit_request(
            project_id,
            editor_user_id=user.id,
            editor_session_id=session_id,
            request_id=request_id,
            approved=approved,
        )
    except ValueError as exc:
        publish_project_event(
            project_id,
            {
                "type": "edit_request_response",
                "project_id": project_id,
                "status": "error",
                "message": str(exc),
                "request_id": request_id,
                "requester": pending.get("requester") or {},
            },
        )
