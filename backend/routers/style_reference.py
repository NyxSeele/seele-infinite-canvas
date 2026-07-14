"""镜头级视频风格参考 API（分镜行 + 独立 video-gen 节点双路径）。"""

from __future__ import annotations

import asyncio
import json
import logging
import uuid
from pathlib import Path

from fastapi import APIRouter, Depends, File, HTTPException, Query, UploadFile
from sqlalchemy.orm import Session

from core.dependencies import get_current_user
from db.session import get_db
from models import Task, User
from schemas.style_reference import StyleReferenceUpdateRequest
from services.canvas_access import get_accessible_project
from services.quota_service import create_task_record
from services.style_reference_service import (
    STYLE_VIDEO_DIR,
    analyze_and_patch_node,
    clear_node_style_reference,
    get_node_style_reference,
    resolve_shot_video_node_id,
    update_node_style_reference,
)
from services.upload_validation import (
    validate_style_video_upload,
    video_suffix_for_mime,
)

router = APIRouter(tags=["style-reference"])
logger = logging.getLogger(__name__)

TASK_TYPE_STYLE_REF = "style_ref"


async def _run_style_ref_task(
    task_id: str,
    *,
    user_id: int,
    project_id: str,
    node_id: str,
    video_path: str,
    declared_mime: str | None,
    script_table_node_id: str | None,
    row_id: str | None,
) -> None:
    from db.session import SessionLocal

    db = SessionLocal()
    path = Path(video_path)
    try:
        task = db.get(Task, task_id)
        if task:
            task.status = "processing"
            task.error = None
            db.commit()

        if not path.is_file():
            raise ValueError("上传视频已丢失，请重新上传")

        content = path.read_bytes()
        user = db.get(User, user_id)
        if not user:
            raise ValueError("用户不存在")

        project = get_accessible_project(db, user, project_id, require_edit=True)
        style_data = await analyze_and_patch_node(
            db,
            project,
            node_id,
            content,
            declared_mime=declared_mime,
            user_id=user_id,
            script_table_node_id=script_table_node_id,
            row_id=row_id,
        )

        task = db.get(Task, task_id)
        if task and task.status != "cancelled":
            task.status = "completed"
            task.error = None
            task.result = json.dumps(style_data, ensure_ascii=False)
            db.commit()
    except HTTPException as e:
        detail = e.detail if isinstance(e.detail, str) else "视频风格分析失败，请稍后重试"
        task = db.get(Task, task_id)
        if task and task.status != "cancelled":
            task.status = "failed"
            task.error = detail[:2000]
            task.result = None
            db.commit()
        logger.warning("style_ref task HTTP fail task_id=%s detail=%s", task_id, detail)
    except Exception as e:
        task = db.get(Task, task_id)
        if task and task.status != "cancelled":
            task.status = "failed"
            task.error = str(e)[:2000]
            task.result = None
            db.commit()
        logger.exception("style_ref async failed task_id=%s", task_id)
    finally:
        try:
            if path.is_file():
                path.unlink()
        except OSError:
            logger.warning("failed to cleanup style_ref staging file %s", path)
        db.close()


def _stage_style_video(content: bytes, declared_mime: str | None) -> tuple[Path, str]:
    mime = validate_style_video_upload(content, declared_mime)
    suffix = video_suffix_for_mime(mime)
    STYLE_VIDEO_DIR.mkdir(parents=True, exist_ok=True)
    staging = STYLE_VIDEO_DIR / f"style_ref_staging_{uuid.uuid4()}{suffix}"
    staging.write_bytes(content)
    return staging, mime


def _enqueue_style_ref(
    *,
    db: Session,
    user: User,
    project_id: str,
    node_id: str,
    content: bytes,
    declared_mime: str | None,
    script_table_node_id: str | None = None,
    row_id: str | None = None,
) -> dict:
    staging, mime = _stage_style_video(content, declared_mime)
    task_id = str(uuid.uuid4())
    create_task_record(
        db,
        task_id,
        TASK_TYPE_STYLE_REF,
        "pending",
        user_id=user.id,
        prompt_text=f"style_ref node={node_id}",
        node_id=node_id,
    )
    db.commit()
    asyncio.create_task(
        _run_style_ref_task(
            task_id,
            user_id=user.id,
            project_id=project_id,
            node_id=node_id,
            video_path=str(staging),
            declared_mime=mime,
            script_table_node_id=script_table_node_id,
            row_id=row_id,
        )
    )
    return {"task_id": task_id, "status": "pending", "node_id": node_id}


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
        return _enqueue_style_ref(
            db=db,
            user=user,
            project_id=project_id,
            node_id=node_id,
            content=content,
            declared_mime=file.content_type,
            script_table_node_id=script_table_node_id,
            row_id=row_id,
        )
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(status_code=503, detail="视频风格分析失败，请稍后重试") from exc


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
    get_accessible_project(db, user, project_id, require_edit=True)
    content = await file.read()
    if not content:
        raise HTTPException(status_code=400, detail="请上传视频文件")
    try:
        return _enqueue_style_ref(
            db=db,
            user=user,
            project_id=project_id,
            node_id=node_id,
            content=content,
            declared_mime=file.content_type,
        )
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(status_code=503, detail="视频风格分析失败，请稍后重试") from exc


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
