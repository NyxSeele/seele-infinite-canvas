from typing import Literal

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from core.dependencies import get_current_user
from db.session import get_db
from models import User
from services.canvas_access import get_accessible_project
from services.document_import_service import (
    apply_document_import,
    cleanup_session,
    group_suggest_for_sheet,
    group_suggest_llm_for_sheet,
    parse_document_sheets_async,
    scan_document,
)

router = APIRouter(prefix="/api/import/document", tags=["import-document"])


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
    try:
        sheets = await parse_document_sheets_async(
            body.import_session_id,
            body.sheet_names,
            try_llm_fix=True,
        )
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(status_code=400, detail=f"解析失败: {exc}") from exc
    return {"sheets": sheets}


@router.post("/group-suggest")
async def group_suggest_import(
    body: GroupSuggestRequest,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    get_accessible_project(db, user, body.project_id)
    try:
        if body.mode == "llm":
            return await group_suggest_llm_for_sheet(
                body.import_session_id,
                body.sheet_name,
            )
        return group_suggest_for_sheet(
            body.import_session_id,
            body.sheet_name,
            target_duration=body.target_duration,
        )
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(status_code=400, detail=f"分组建议失败: {exc}") from exc


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
