import asyncio
import json
import logging
import uuid
from typing import Literal

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from core.dependencies import get_current_user
from db.session import get_db
from models import Task, User
from services.canvas_access import get_accessible_project
from services.document_import_service import (
    apply_document_import,
    cleanup_session,
    group_suggest_for_sheet,
    group_suggest_llm_for_sheet,
    parse_document_sheets_async,
    scan_document,
)
from services.quota_service import create_task_record

router = APIRouter(prefix="/api/import/document", tags=["import-document"])
logger = logging.getLogger(__name__)

TASK_TYPE_PARSE = "imp_parse"
TASK_TYPE_GROUP = "imp_group"


class ParseImportRequest(BaseModel):
    project_id: str = Field(..., min_length=1)
    import_session_id: str = Field(..., min_length=1)
    sheet_names: list[str] = Field(default_factory=list)


class GroupSuggestRequest(BaseModel):
    project_id: str = Field(..., min_length=1)
    import_session_id: str = Field(..., min_length=1)
    sheet_name: str = Field(..., min_length=1)
    mode: Literal["rule", "llm"] = "rule"
    target_duration: float = Field(default=10.0, ge=2.0, le=15.0)


class OutlineApplyItem(BaseModel):
    confirmed: bool = False
    sheet_name: str = "__word__"
    text: str = ""
    content_hash: str = ""
    label: str | None = None
    replace_node_id: str | None = None


class ShotTableApplyItem(BaseModel):
    confirmed: bool = False
    sheet_name: str
    label: str | None = None
    rows: list[dict] = Field(default_factory=list)
    segments: list[dict] = Field(default_factory=list)
    content_hash: str = ""
    replace_node_id: str | None = None
    groups: list[list[int]] | None = None
    micro_rows: list[dict] | None = None


class ApplyImportRequest(BaseModel):
    project_id: str = Field(..., min_length=1)
    import_session_id: str | None = None
    cleanup_session: bool = False
    outline: OutlineApplyItem | None = None
    shot_tables: list[ShotTableApplyItem] = Field(default_factory=list)


def _mark_json_task_done(
    db: Session, task_id: str, *, result: dict | None = None, error: str | None = None
) -> None:
    task = db.get(Task, task_id)
    if not task or task.status == "cancelled":
        return
    if error:
        task.status = "failed"
        task.error = error[:2000]
        task.result = None
    else:
        task.status = "completed"
        task.error = None
        task.result = json.dumps(result or {}, ensure_ascii=False)
    db.commit()


async def _run_parse_task(
    task_id: str, import_session_id: str, sheet_names: list[str]
) -> None:
    from db.session import SessionLocal

    db = SessionLocal()
    try:
        task = db.get(Task, task_id)
        if task:
            task.status = "processing"
            task.error = None
            db.commit()
        sheets = await parse_document_sheets_async(
            import_session_id,
            sheet_names,
            try_llm_fix=True,
        )
        _mark_json_task_done(db, task_id, result={"sheets": sheets})
    except FileNotFoundError as exc:
        _mark_json_task_done(db, task_id, error=str(exc))
    except Exception as exc:
        logger.exception("import parse async failed task_id=%s", task_id)
        _mark_json_task_done(db, task_id, error=f"解析失败: {str(exc)[:200]}")
    finally:
        db.close()


async def _run_group_llm_task(
    task_id: str, import_session_id: str, sheet_name: str
) -> None:
    from db.session import SessionLocal

    db = SessionLocal()
    try:
        task = db.get(Task, task_id)
        if task:
            task.status = "processing"
            task.error = None
            db.commit()
        result = await group_suggest_llm_for_sheet(import_session_id, sheet_name)
        if not isinstance(result, dict):
            result = {"data": result}
        _mark_json_task_done(db, task_id, result=result)
    except FileNotFoundError as exc:
        _mark_json_task_done(db, task_id, error=str(exc))
    except Exception as exc:
        logger.exception("import group-suggest llm async failed task_id=%s", task_id)
        _mark_json_task_done(db, task_id, error=f"分组建议失败: {str(exc)[:200]}")
    finally:
        db.close()


@router.post("/scan")
async def scan_import_document(
    project_id: str = Form(...),
    file: UploadFile = File(...),
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    get_accessible_project(db, user, project_id)
    raw = await file.read()
    if not raw:
        raise HTTPException(status_code=400, detail="空文件")
    try:
        result = scan_document(db, project_id, raw, file.filename or "upload.xlsx")
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(status_code=400, detail=f"文件解析失败: {exc}") from exc
    return result


@router.post("/parse")
async def parse_import_document(
    body: ParseImportRequest,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    get_accessible_project(db, user, body.project_id)
    task_id = str(uuid.uuid4())
    create_task_record(
        db,
        task_id,
        TASK_TYPE_PARSE,
        "queued",
        user_id=user.id,
        prompt_text=body.import_session_id[:200],
    )
    db.commit()
    asyncio.create_task(
        _run_parse_task(task_id, body.import_session_id, list(body.sheet_names or []))
    )
    return {"task_id": task_id, "status": "queued"}


@router.post("/group-suggest")
async def group_suggest_import(
    body: GroupSuggestRequest,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    get_accessible_project(db, user, body.project_id)
    try:
        if body.mode != "llm":
            return group_suggest_for_sheet(
                body.import_session_id,
                body.sheet_name,
                target_duration=body.target_duration,
            )
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(status_code=400, detail=f"分组建议失败: {exc}") from exc

    task_id = str(uuid.uuid4())
    create_task_record(
        db,
        task_id,
        TASK_TYPE_GROUP,
        "queued",
        user_id=user.id,
        prompt_text=f"{body.import_session_id}:{body.sheet_name}"[:200],
    )
    db.commit()
    asyncio.create_task(
        _run_group_llm_task(task_id, body.import_session_id, body.sheet_name)
    )
    return {"task_id": task_id, "status": "queued"}


@router.post("/apply")
def apply_import(
    body: ApplyImportRequest,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    project = get_accessible_project(db, user, body.project_id)
    try:
        result = apply_document_import(
            db,
            project,
            {
                "import_session_id": body.import_session_id,
                "outline": body.outline.model_dump() if body.outline else None,
                "shot_tables": [t.model_dump() for t in body.shot_tables],
            },
        )
    except ValueError as exc:
        db.rollback()
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception as exc:
        db.rollback()
        raise HTTPException(status_code=400, detail=f"导入失败: {exc}") from exc
    if body.cleanup_session and body.import_session_id:
        cleanup_session(body.import_session_id)
    return result
