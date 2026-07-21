"""项目级生成记忆 API。"""

from __future__ import annotations

from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from core.dependencies import get_current_user
from db.session import get_db
from models import User
from services.canvas_access import get_accessible_project
from services.generation_memory_service import (
    get_project_generation_memory,
    update_project_generation_memory,
)

router = APIRouter(tags=["generation-memory"])


class GenerationMemoryResponse(BaseModel):
    project_id: str
    generation_memory: dict


class GenerationMemoryUpdateRequest(BaseModel):
    protagonist_face_url: str | None = Field(default=None)
    preferred_video_model: str | None = Field(default=None)
    preferred_image_model: str | None = Field(default=None)
    lut_preset_id: str | None = Field(default=None)
    last_ratio: str | None = Field(default=None)
    last_quality: str | None = Field(default=None)


@router.get("/api/projects/{project_id}/generation-memory")
def get_generation_memory(
    project_id: str,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    project = get_accessible_project(db, user, project_id)
    return GenerationMemoryResponse(
        project_id=project_id,
        generation_memory=get_project_generation_memory(project),
    )


@router.put("/api/projects/{project_id}/generation-memory")
def put_generation_memory(
    project_id: str,
    body: GenerationMemoryUpdateRequest,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    project = get_accessible_project(db, user, project_id, require_edit=True)
    patch = body.model_dump(exclude_unset=True)
    memory = update_project_generation_memory(project, patch)
    db.commit()
    return GenerationMemoryResponse(project_id=project_id, generation_memory=memory)
