"""项目 LUT 配置 API。"""

from __future__ import annotations

import uuid
from pathlib import Path

from fastapi import APIRouter, Depends, File, HTTPException, Query, UploadFile
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from core.dependencies import get_current_user
from db.session import get_db
from models import User
from services.canvas_access import get_accessible_project
from services.lut_canvas import (
    get_script_table_lut_config,
    iter_video_nodes_with_source,
    lut_is_configured,
    patch_script_table_lut,
    resolve_active_lut_from_table,
)
from services.canvas_style_ref import load_canvas_data

router = APIRouter(tags=["lut"])

MAX_LUT_BYTES = 5 * 1024 * 1024
UPLOADS_LUTS = Path(__file__).resolve().parent.parent / "uploads" / "luts"


class LutConfigUpdateRequest(BaseModel):
    script_table_node_id: str = Field(..., description="分镜表节点 ID")
    lut_preset: str | None = Field(default=None, description="内置预设 id 或 none")
    clear_custom: bool = Field(default=False, description="清除自定义 LUT")


@router.get("/api/projects/{project_id}/lut")
def get_project_lut(
    project_id: str,
    script_table_node_id: str = Query(...),
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    project = get_accessible_project(db, user, project_id)
    canvas_data = load_canvas_data(project)
    return get_script_table_lut_config(canvas_data, script_table_node_id)


@router.put("/api/projects/{project_id}/lut")
def update_project_lut(
    project_id: str,
    body: LutConfigUpdateRequest,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    project = get_accessible_project(db, user, project_id, require_edit=True)
    return patch_script_table_lut(
        project,
        body.script_table_node_id,
        lut_preset=body.lut_preset,
        clear_custom=body.clear_custom,
    )


@router.post("/api/lut/upload")
async def upload_lut_file(
    project_id: str = Query(...),
    script_table_node_id: str = Query(...),
    file: UploadFile = File(...),
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    project = get_accessible_project(db, user, project_id, require_edit=True)
    filename = (file.filename or "").strip().lower()
    if not filename.endswith(".cube"):
        raise HTTPException(status_code=400, detail="仅支持 .cube 文件")
    raw = await file.read()
    if len(raw) > MAX_LUT_BYTES:
        raise HTTPException(status_code=400, detail="LUT 文件不能超过 5MB")
    if not raw:
        raise HTTPException(status_code=400, detail="文件为空")

    dest_dir = UPLOADS_LUTS / project_id
    dest_dir.mkdir(parents=True, exist_ok=True)
    dest_name = f"{uuid.uuid4().hex}.cube"
    dest_path = dest_dir / dest_name
    dest_path.write_bytes(raw)

    url = f"/api/uploads/luts/{project_id}/{dest_name}"
    display_name = file.filename or dest_name
    return patch_script_table_lut(
        project,
        script_table_node_id,
        lut_custom_url=url,
        lut_custom_name=display_name,
    )


class LutApplyAllRequest(BaseModel):
    script_table_node_id: str


@router.post("/api/projects/{project_id}/lut/apply-all")
async def apply_lut_to_all_videos(
    project_id: str,
    body: LutApplyAllRequest,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    from services.lut_task_service import queue_video_lut_task

    project = get_accessible_project(db, user, project_id, require_edit=True)
    canvas_data = load_canvas_data(project)
    if not lut_is_configured(canvas_data, body.script_table_node_id):
        raise HTTPException(status_code=400, detail="请先选择 LUT 预设或上传自定义 LUT")

    lut_preset, lut_custom_url = resolve_active_lut_from_table(
        canvas_data, body.script_table_node_id
    )
    nodes = iter_video_nodes_with_source(canvas_data)
    task_ids: list[str] = []
    for item in nodes:
        task_id = await queue_video_lut_task(
            db=db,
            user=user,
            video_url=item["video_url"],
            node_id=item["node_id"],
            project_id=project_id,
            script_table_node_id=body.script_table_node_id,
            lut_preset=lut_preset,
            lut_custom_url=lut_custom_url,
        )
        if task_id:
            task_ids.append(task_id)
    return {"queued": len(task_ids), "task_ids": task_ids}
