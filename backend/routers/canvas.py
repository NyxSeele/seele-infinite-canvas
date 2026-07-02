import json
import uuid
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, File, HTTPException, Query, UploadFile
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from core.datetime_utils import to_utc_iso
from core.dependencies import get_current_user
from db.session import get_db
from models import User
from models.canvas import CanvasState
from models.canvas_project import CanvasProject
from models.canvas_share import CanvasShare, new_share_token
from services.canvas_access import (
    get_accessible_project,
    list_projects_query,
    migrate_project_to_team,
)
from services.canvas_comments import (
    add_comment,
    delete_message,
    list_project_comments,
    reply_comment,
    update_message,
)
from services.canvas_lock import (
    acquire_lock,
    get_lock,
    heartbeat_lock,
    is_editor,
    publish_canvas_updated,
    release_lock,
)
from services.canvas_presence import leave_presence, list_presence, touch_presence
from services.team_service import require_team_editor

router = APIRouter(prefix="/api/canvas", tags=["canvas"])


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _migrate_canvas_nodes(nodes: list) -> None:
    for node in nodes:
        if node.get("type") == "image-upload":
            node["type"] = "image-gen"


def _parse_canvas_data(data_str: str) -> dict:
    try:
        data = json.loads(data_str or "{}")
        if not isinstance(data, dict):
            return {"nodes": [], "edges": []}
        nodes = data.get("nodes")
        if isinstance(nodes, list):
            _migrate_canvas_nodes(nodes)
        return {
            "nodes": data.get("nodes") or [],
            "edges": data.get("edges") or [],
        }
    except Exception:
        return {"nodes": [], "edges": []}


def _preview_from_data(data_str: str) -> str | None:
    try:
        data = json.loads(data_str or "{}")
        for node in data.get("nodes") or []:
            payload = node.get("data") or {}
            for key in ("imageUrl", "uploadedImage", "generatedImage", "videoUrl"):
                val = payload.get(key)
                if isinstance(val, str) and val.strip():
                    return val.strip()
            results = payload.get("results")
            if isinstance(results, list):
                for item in results:
                    if isinstance(item, str) and item.strip():
                        return item.strip()
    except Exception:
        return None
    return None


def _node_count(data_str: str) -> int:
    try:
        data = json.loads(data_str or "{}")
        nodes = data.get("nodes")
        return len(nodes) if isinstance(nodes, list) else 0
    except Exception:
        return 0


def _project_summary(row: CanvasProject) -> dict:
    return {
        "id": row.id,
        "name": row.name,
        "team_id": row.team_id,
        "version": int(row.version or 1),
        "updated_at": to_utc_iso(row.updated_at),
        "last_modified_by": row.last_modified_by,
        "node_count": _node_count(row.data),
        "preview_url": _preview_from_data(row.data),
    }


def _latest_project(db: Session, user_id: int) -> CanvasProject | None:
    return (
        db.query(CanvasProject)
        .filter(CanvasProject.user_id == user_id, CanvasProject.team_id.is_(None))
        .order_by(CanvasProject.updated_at.desc())
        .first()
    )


def _legacy_migrate_user(db: Session, user: User) -> CanvasProject | None:
    existing = _latest_project(db, user.id)
    if existing:
        return existing
    legacy = db.query(CanvasState).filter(CanvasState.user_id == user.id).first()
    if not legacy:
        return None
    row = CanvasProject(
        id=str(uuid.uuid4()),
        user_id=user.id,
        team_id=None,
        name="未命名画布",
        data=legacy.data or '{"nodes":[],"edges":[]}',
        version=1,
        created_at=legacy.updated_at or _utcnow(),
        updated_at=legacy.updated_at or _utcnow(),
    )
    db.add(row)
    db.commit()
    db.refresh(row)
    return row


class CanvasSaveRequest(BaseModel):
    canvas_data: dict


class CanvasShareRequest(BaseModel):
    canvas_data: dict
    project_name: str = "未命名画布"


class ProjectCreateRequest(BaseModel):
    name: str = Field(default="未命名画布", max_length=256)
    canvas_data: dict | None = None
    team_id: str | None = None


class ProjectUpdateRequest(BaseModel):
    canvas_data: dict | None = None
    name: str | None = Field(default=None, max_length=256)
    version: int | None = None


class ProjectMigrateToTeamRequest(BaseModel):
    team_id: str = Field(..., min_length=1, max_length=36)


class PresencePingRequest(BaseModel):
    is_editor: bool = False
    username: str | None = Field(None, max_length=64)
    display_name: str | None = Field(None, max_length=64)


class SessionAcquireRequest(BaseModel):
    display_name: str | None = Field(None, max_length=64)


class SessionHeartbeatRequest(BaseModel):
    session_id: str


class SessionReleaseRequest(BaseModel):
    session_id: str


class CommentCreateRequest(BaseModel):
    node_id: str = Field(..., max_length=128)
    body: str = Field(..., max_length=200)
    display_name: str | None = Field(None, max_length=64)
    mentioned_user_ids: list[int] = Field(default_factory=list)


class CommentReplyRequest(BaseModel):
    body: str = Field(..., max_length=200)
    display_name: str | None = Field(None, max_length=64)
    mentioned_user_ids: list[int] = Field(default_factory=list)


class CommentUpdateRequest(BaseModel):
    body: str = Field(..., max_length=200)


@router.get("/projects")
def list_canvas_projects(
    team_id: str | None = Query(default=None),
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    if team_id is None:
        _legacy_migrate_user(db, user)
    rows = list_projects_query(db, user, team_id).all()
    return {"projects": [_project_summary(row) for row in rows]}


@router.post("/projects")
def create_canvas_project(
    body: ProjectCreateRequest,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    now = _utcnow()
    if body.team_id:
        require_team_editor(db, body.team_id, user)
    canvas_data = body.canvas_data if isinstance(body.canvas_data, dict) else {"nodes": [], "edges": []}
    nodes = canvas_data.get("nodes")
    if isinstance(nodes, list):
        _migrate_canvas_nodes(nodes)
    name = (body.name or "未命名画布").strip()[:256] or "未命名画布"
    row = CanvasProject(
        id=str(uuid.uuid4()),
        user_id=user.id,
        team_id=body.team_id,
        name=name,
        data=json.dumps(canvas_data, ensure_ascii=False),
        version=1,
        created_at=now,
        updated_at=now,
    )
    db.add(row)
    db.commit()
    return _project_summary(row)


@router.get("/projects/{project_id}")
def get_canvas_project(
    project_id: str,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    row = get_accessible_project(db, user, project_id)
    canvas_data = _parse_canvas_data(row.data)
    lock = get_lock(project_id)
    return {
        **_project_summary(row),
        "canvas_data": canvas_data,
        "lock": lock,
    }


@router.get("/projects/{project_id}/presence")
def get_canvas_presence(
    project_id: str,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """在线成员列表（HTTP 轮询兜底，与 WebSocket presence 共用 Redis）。"""
    get_accessible_project(db, user, project_id)
    members = list_presence(project_id)
    return {"members": members}


@router.post("/projects/{project_id}/presence/ping")
def ping_canvas_presence(
    project_id: str,
    body: PresencePingRequest | None = None,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    get_accessible_project(db, user, project_id)
    req = body or PresencePingRequest()
    uname = (req.username or user.username or str(user.id)).strip()
    label = (
        (user.display_name or "").strip()
        or (req.display_name or "").strip()
        or uname
    )
    members = touch_presence(
        project_id,
        user.id,
        uname,
        is_editor=bool(req.is_editor),
        avatar_url=(user.avatar_url or "").strip(),
        display_name=label,
        email=(user.email or "").strip(),
    )
    return {"members": members}


@router.post("/projects/{project_id}/presence/leave")
def leave_canvas_presence(
    project_id: str,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """离开画布时立即从在线列表移除（勿等 TTL）。"""
    get_accessible_project(db, user, project_id)
    members = leave_presence(project_id, user.id)
    return {"members": members}


@router.put("/projects/{project_id}")
def update_canvas_project(
    project_id: str,
    body: ProjectUpdateRequest,
    session_id: str | None = Query(default=None),
    display_name: str | None = Query(default=None, max_length=64),
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    row = get_accessible_project(db, user, project_id, require_edit=True)
    if not is_editor(project_id, user.id, session_id):
        raise HTTPException(status_code=423, detail="当前画布由其他用户编辑中")

    if body.version is not None and int(body.version) != int(row.version or 1):
        raise HTTPException(
            status_code=409,
            detail={
                "message": "版本冲突",
                "version": int(row.version or 1),
                "canvas_data": _parse_canvas_data(row.data),
                "name": row.name,
            },
        )

    if body.name is not None:
        row.name = (body.name or "未命名画布").strip()[:256] or "未命名画布"
    author_label = (display_name or "").strip() or user.username
    if body.canvas_data is not None:
        nodes = body.canvas_data.get("nodes")
        if isinstance(nodes, list):
            _migrate_canvas_nodes(nodes)
        row.data = json.dumps(body.canvas_data, ensure_ascii=False)
        row.last_modified_by = author_label[:64] if author_label else None
    row.version = int(row.version or 1) + 1
    row.updated_at = _utcnow()
    db.commit()
    db.refresh(row)
    publish_canvas_updated(
        project_id,
        version=int(row.version),
        user_id=user.id,
        username=user.username,
        display_name=author_label,
        name=row.name,
    )
    return _project_summary(row)


@router.delete("/projects/{project_id}")
def delete_canvas_project(
    project_id: str,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    row = get_accessible_project(db, user, project_id, require_edit=True)
    db.delete(row)
    db.commit()
    return {"success": True}


@router.post("/projects/{project_id}/migrate-to-team")
def migrate_canvas_project_to_team(
    project_id: str,
    body: ProjectMigrateToTeamRequest,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """将个人画布迁入团队，团队成员可见可协作。"""
    row = migrate_project_to_team(db, user, project_id, body.team_id)
    return _project_summary(row)


@router.post("/projects/{project_id}/session/join")
def join_canvas_session(
    project_id: str,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """加入画布房间（不抢编辑锁）。"""
    get_accessible_project(db, user, project_id)
    lock = get_lock(project_id)
    is_me = bool(lock and int(lock.get("user_id", -1)) == int(user.id))
    return {
        "project_id": project_id,
        "lock": lock,
        "is_editor": is_me,
    }


@router.post("/projects/{project_id}/session")
def acquire_canvas_session(
    project_id: str,
    body: SessionAcquireRequest | None = None,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    get_accessible_project(db, user, project_id)
    label = (body.display_name if body else None) or user.username
    result = acquire_lock(project_id, user.id, user.username, display_name=label)
    return {
        "project_id": project_id,
        "editor": result["editor"],
        "session_id": result["session_id"],
        "kicked": result.get("kicked"),
        "lock": result.get("lock"),
    }


@router.post("/projects/{project_id}/session/heartbeat")
def canvas_session_heartbeat(
    project_id: str,
    body: SessionHeartbeatRequest,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    get_accessible_project(db, user, project_id)
    ok = heartbeat_lock(project_id, user.id, body.session_id)
    if not ok:
        raise HTTPException(status_code=423, detail="编辑会话已失效或被顶号")
    return {"ok": True}


@router.delete("/projects/{project_id}/session")
def release_canvas_session(
    project_id: str,
    session_id: str = Query(...),
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    get_accessible_project(db, user, project_id)
    release_lock(project_id, user.id, session_id)
    return {"ok": True}


@router.post("/save")
def save_canvas(
    body: CanvasSaveRequest,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    row = _latest_project(db, user.id) or _legacy_migrate_user(db, user)
    data_str = json.dumps(body.canvas_data, ensure_ascii=False)
    nodes = body.canvas_data.get("nodes")
    if isinstance(nodes, list):
        _migrate_canvas_nodes(nodes)
    if row:
        row.data = data_str
        row.version = int(row.version or 1) + 1
        row.updated_at = _utcnow()
    else:
        row = CanvasProject(
            id=str(uuid.uuid4()),
            user_id=user.id,
            team_id=None,
            name="未命名画布",
            data=data_str,
            version=1,
            created_at=_utcnow(),
            updated_at=_utcnow(),
        )
        db.add(row)
    db.commit()
    return {"success": True, "project_id": row.id, "version": row.version}


@router.get("/load")
def load_canvas(
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    row = _latest_project(db, user.id) or _legacy_migrate_user(db, user)
    if not row:
        return {"nodes": [], "edges": [], "project_id": None, "project_name": None}
    canvas_data = _parse_canvas_data(row.data)
    return {
        **canvas_data,
        "project_id": row.id,
        "project_name": row.name,
        "version": row.version,
    }


@router.post("/share")
def create_canvas_share(
    body: CanvasShareRequest,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    token = new_share_token()
    row = CanvasShare(
        id=token,
        user_id=user.id,
        project_name=(body.project_name or "未命名画布").strip()[:256] or "未命名画布",
        data=json.dumps(body.canvas_data, ensure_ascii=False),
    )
    db.add(row)
    db.commit()
    return {
        "token": token,
        "project_name": row.project_name,
        "url_path": f"/canvas?share={token}",
    }


@router.get("/share/{token}")
def load_canvas_share(token: str, db: Session = Depends(get_db)):
    row = db.query(CanvasShare).filter(CanvasShare.id == token).first()
    if not row:
        raise HTTPException(status_code=404, detail="分享链接无效或已过期")
    try:
        canvas_data = json.loads(row.data)
        nodes = canvas_data.get("nodes")
        if isinstance(nodes, list):
            _migrate_canvas_nodes(nodes)
    except Exception as exc:
        raise HTTPException(status_code=500, detail="分享数据损坏") from exc
    return {
        "project_name": row.project_name,
        "canvas_data": canvas_data,
        "read_only": True,
    }


@router.get("/projects/{project_id}/comments")
def get_project_comments(
    project_id: str,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    get_accessible_project(db, user, project_id)
    return {"threads": list_project_comments(db, project_id)}


@router.post("/projects/{project_id}/comments")
def create_project_comment(
    project_id: str,
    body: CommentCreateRequest,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    get_accessible_project(db, user, project_id)
    author_name = (body.display_name or "").strip() or user.username
    thread = add_comment(
        db,
        project_id=project_id,
        node_id=body.node_id.strip(),
        body=body.body,
        user_id=user.id,
        username=author_name,
        mentioned_user_ids=body.mentioned_user_ids,
    )
    return {"thread": thread}


@router.post("/projects/{project_id}/comments/{thread_id}/replies")
def reply_project_comment(
    project_id: str,
    thread_id: str,
    body: CommentReplyRequest,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    get_accessible_project(db, user, project_id)
    author_name = (body.display_name or "").strip() or user.username
    thread = reply_comment(
        db,
        project_id=project_id,
        thread_id=thread_id,
        body=body.body,
        user_id=user.id,
        username=author_name,
        mentioned_user_ids=body.mentioned_user_ids,
    )
    return {"thread": thread}


@router.put("/projects/{project_id}/comments/messages/{message_id}")
def edit_project_comment_message(
    project_id: str,
    message_id: str,
    body: CommentUpdateRequest,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    get_accessible_project(db, user, project_id)
    thread = update_message(
        db,
        project_id=project_id,
        message_id=message_id,
        body=body.body,
        user_id=user.id,
    )
    return {"thread": thread}


@router.delete("/projects/{project_id}/comments/messages/{message_id}")
def remove_project_comment_message(
    project_id: str,
    message_id: str,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    get_accessible_project(db, user, project_id)
    thread = delete_message(
        db,
        project_id=project_id,
        message_id=message_id,
        user_id=user.id,
    )
    if isinstance(thread, dict) and thread.get("deleted"):
        return {"thread": None, **thread}
    if thread is None:
        return {"thread": None, "deleted": True}
    return {"thread": thread, "deleted": False}
