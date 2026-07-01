"""镜头级视频风格参考 API（分镜行 + 独立 video-gen 节点双路径）。"""

from __future__ import annotations

from fastapi import APIRouter, Depends, File, HTTPException, Query, UploadFile
from sqlalchemy.orm import Session

from core.dependencies import get_current_user
from db.session import get_db
from models import User
from schemas.style_reference import StyleReferenceUpdateRequest
from services.canvas_access import get_accessible_project
from services.style_reference_service import (
    analyze_and_patch_node,
    clear_node_style_reference,
    get_node_style_reference,
    resolve_shot_video_node_id,
    update_node_style_reference,
)

router = APIRouter(tags=["style-reference"])


@router.get("/api/shots/{row_id}/style-reference")
def get_shot_style_reference(
    row_id: str,
    project_id: str = Query(..., description="画布项目 ID"),
    script_table_node_id: str = Query(..., description="分镜表节点 ID"),
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    project = get_accessible_project(db, user, project_id)
    node_id = resolve_shot_video_node_id(project, script_table_node_id, row_id)
    return {
        "style_reference": get_node_style_reference(project, node_id),
        "node_id": node_id,
    }


@router.post("/api/shots/{row_id}/style-reference")
async def upload_shot_style_reference(
    row_id: str,
    file: UploadFile = File(...),
    project_id: str = Query(...),
    script_table_node_id: str = Query(...),
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    project = get_accessible_project(db, user, project_id, require_edit=True)
    node_id = resolve_shot_video_node_id(project, script_table_node_id, row_id)
    content = await file.read()
    if not content:
        raise HTTPException(status_code=400, detail="请上传视频文件")
    try:
        style_data = await analyze_and_patch_node(
            db,
            project,
            node_id,
            content,
            declared_mime=file.content_type,
            user_id=user.id,
            script_table_node_id=script_table_node_id,
            row_id=row_id,
        )
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(status_code=503, detail="视频风格分析失败，请稍后重试") from exc
    return {"style_reference": style_data, "node_id": node_id}


@router.put("/api/shots/{row_id}/style-reference")
def put_shot_style_reference(
    row_id: str,
    body: StyleReferenceUpdateRequest,
    project_id: str = Query(...),
    script_table_node_id: str = Query(...),
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    project = get_accessible_project(db, user, project_id, require_edit=True)
    node_id = resolve_shot_video_node_id(project, script_table_node_id, row_id)
    if not get_node_style_reference(project, node_id):
        raise HTTPException(status_code=404, detail="该镜头未设定风格参考")
    patch = body.model_dump(exclude_unset=True)
    updated = update_node_style_reference(
        project,
        node_id,
        patch,
        script_table_node_id=script_table_node_id,
        row_id=row_id,
    )
    db.commit()
    return {"style_reference": updated, "node_id": node_id}


@router.delete("/api/shots/{row_id}/style-reference")
def delete_shot_style_reference(
    row_id: str,
    project_id: str = Query(...),
    script_table_node_id: str = Query(...),
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    project = get_accessible_project(db, user, project_id, require_edit=True)
    node_id = resolve_shot_video_node_id(project, script_table_node_id, row_id)
    clear_node_style_reference(
        project,
        node_id,
        script_table_node_id=script_table_node_id,
        row_id=row_id,
    )
    db.commit()
    return {"success": True, "node_id": node_id}


@router.get("/api/video-nodes/{node_id}/style-reference")
def get_video_node_style_reference(
    node_id: str,
    project_id: str = Query(...),
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    project = get_accessible_project(db, user, project_id)
    return {"style_reference": get_node_style_reference(project, node_id)}


@router.post("/api/video-nodes/{node_id}/style-reference")
async def upload_video_node_style_reference(
    node_id: str,
    file: UploadFile = File(...),
    project_id: str = Query(...),
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    project = get_accessible_project(db, user, project_id, require_edit=True)
    content = await file.read()
    if not content:
        raise HTTPException(status_code=400, detail="请上传视频文件")
    try:
        style_data = await analyze_and_patch_node(
            db,
            project,
            node_id,
            content,
            declared_mime=file.content_type,
            user_id=user.id,
        )
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(status_code=503, detail="视频风格分析失败，请稍后重试") from exc
    return {"style_reference": style_data}


@router.put("/api/video-nodes/{node_id}/style-reference")
def put_video_node_style_reference(
    node_id: str,
    body: StyleReferenceUpdateRequest,
    project_id: str = Query(...),
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    project = get_accessible_project(db, user, project_id, require_edit=True)
    if not get_node_style_reference(project, node_id):
        raise HTTPException(status_code=404, detail="该节点未设定风格参考")
    patch = body.model_dump(exclude_unset=True)
    updated = update_node_style_reference(project, node_id, patch)
    db.commit()
    return {"style_reference": updated}


@router.delete("/api/video-nodes/{node_id}/style-reference")
def delete_video_node_style_reference(
    node_id: str,
    project_id: str = Query(...),
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    project = get_accessible_project(db, user, project_id, require_edit=True)
    clear_node_style_reference(project, node_id)
    db.commit()
    return {"success": True}
