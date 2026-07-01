import asyncio
from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from core.dependencies import get_current_user
from db.session import get_db
from models import User
from services.canvas_access import get_accessible_project
from services.export_service import (
    create_export_job_record,
    export_job_to_dict,
    get_export_job_for_user,
    run_export_job,
)

router = APIRouter(prefix="/api/exports", tags=["exports"])

_UPLOAD_ROOT = Path("uploads")


class CreateExportRequest(BaseModel):
    project_id: str = Field(..., min_length=1)
    script_table_node_id: str = Field(..., min_length=1)


@router.post("")
async def create_export(
    body: CreateExportRequest,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    get_accessible_project(db, user, body.project_id)
    job = create_export_job_record(
        db,
        project_id=body.project_id,
        script_table_node_id=body.script_table_node_id,
        user_id=user.id,
    )
    asyncio.create_task(run_export_job(job.id))
    return export_job_to_dict(job)


@router.get("/{export_id}")
def get_export(
    export_id: str,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    job = get_export_job_for_user(db, export_id, user.id)
    return export_job_to_dict(job)


@router.get("/{export_id}/download")
def download_export(
    export_id: str,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    job = get_export_job_for_user(db, export_id, user.id)
    if job.status != "completed" or not job.file_path:
        raise HTTPException(status_code=400, detail="导出尚未完成")
    file_path = (_UPLOAD_ROOT / job.file_path).resolve()
    root = _UPLOAD_ROOT.resolve()
    if not str(file_path).startswith(str(root)) or not file_path.is_file():
        raise HTTPException(status_code=404, detail="导出文件不存在")
    filename = file_path.name
    return FileResponse(
        file_path,
        media_type="application/zip",
        filename=filename,
    )
