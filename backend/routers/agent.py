from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import StreamingResponse
from sqlalchemy.orm import Session

from core.dependencies import get_current_user
from db.session import get_db
from models import User
from schemas.agent_schemas import (
    AgentChatArchiveListResponse,
    AgentChatArchiveSaveRequest,
    AgentChatTitleRequest,
    AgentChatTitleResponse,
    AgentConversationResponse,
    AgentConversationSaveRequest,
    AgentRunRequest,
    PipelineManifestResponse,
)
from services.agent_conversation_service import (
    get_conversation_messages,
    save_conversation_messages,
)
from services.agent_chat_history_service import (
    delete_chat_archive,
    list_chat_archives,
    save_chat_archive,
)
from services.agent_service import run_agent_stream, generate_chat_title
from services.canvas_access import get_accessible_project
from services.pipeline_manifest import PipelineManifestError, load_pipeline, manifest_to_api_dict
from services.rate_limit import check_agent_rate_limit

router = APIRouter(prefix="/api/agent", tags=["agent"])


@router.get("/pipeline/{name}", response_model=PipelineManifestResponse)
def get_agent_pipeline_manifest(
    name: str,
    current_user: User = Depends(get_current_user),
):
    try:
        manifest = load_pipeline(name)
    except PipelineManifestError as exc:
        detail = str(exc)
        if "not found" in detail:
            raise HTTPException(status_code=404, detail="pipeline manifest not found") from exc
        raise HTTPException(status_code=500, detail="pipeline manifest invalid") from exc
    return PipelineManifestResponse(**manifest_to_api_dict(manifest))


@router.get("/conversation/{project_id}", response_model=AgentConversationResponse)
def get_agent_conversation(
    project_id: str,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    get_accessible_project(db, current_user, project_id, require_edit=True)
    messages = get_conversation_messages(db, current_user.id, project_id)
    return AgentConversationResponse(project_id=project_id, messages=messages)


@router.put("/conversation/{project_id}")
def save_agent_conversation(
    project_id: str,
    body: AgentConversationSaveRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    get_accessible_project(db, current_user, project_id, require_edit=True)
    payload = [m.model_dump(exclude_none=True) for m in body.messages]
    save_conversation_messages(db, current_user.id, project_id, payload)
    return {"ok": True}


@router.get("/chat-history/{project_id}", response_model=AgentChatArchiveListResponse)
def list_agent_chat_history(
    project_id: str,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    get_accessible_project(db, current_user, project_id, require_edit=True)
    entries = list_chat_archives(db, current_user.id, project_id)
    return AgentChatArchiveListResponse(project_id=project_id, entries=entries)


@router.put("/chat-history/{project_id}")
def save_agent_chat_history_entry(
    project_id: str,
    body: AgentChatArchiveSaveRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    get_accessible_project(db, current_user, project_id, require_edit=True)
    payload = [m.model_dump(exclude_none=True) for m in body.messages]
    entry = save_chat_archive(
        db,
        current_user.id,
        project_id,
        payload,
        archive_id=body.id,
        title=body.title,
    )
    return entry


@router.delete("/chat-history/{project_id}/{archive_id}")
def delete_agent_chat_history_entry(
    project_id: str,
    archive_id: str,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    get_accessible_project(db, current_user, project_id, require_edit=True)
    if not delete_chat_archive(db, current_user.id, project_id, archive_id):
        raise HTTPException(status_code=404, detail="历史记录不存在")
    return {"ok": True}


@router.post("/chat-title", response_model=AgentChatTitleResponse)
async def generate_agent_chat_title(
    body: AgentChatTitleRequest,
    current_user: User = Depends(get_current_user),
):
    check_agent_rate_limit(current_user.id)
    payload = [m.model_dump(exclude_none=True) for m in body.messages]
    title = await generate_chat_title(payload)
    return AgentChatTitleResponse(title=title)


@router.post("/run")
async def run_agent(
    request: AgentRunRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    get_accessible_project(db, current_user, request.project_id, require_edit=True)
    check_agent_rate_limit(current_user.id)

    return StreamingResponse(
        run_agent_stream(request),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",
        },
    )
