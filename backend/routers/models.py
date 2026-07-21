from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from comfyui import client as comfyui
from core.dependencies import get_current_user
from db.session import get_db
from model_checker import check_registered_model_available
from models import RegisteredModel, User
from schemas.tasks import SelectModelRequest
from services.model_permission_service import user_can_use_model
from model_registry import COMFYUI_PROVIDER_MAP, MODEL_MAP, MODEL_SUMMARY_OVERRIDES

router = APIRouter(prefix="/api/models", tags=["models"])


def _model_summary(model_id: str) -> str:
    meta = MODEL_MAP.get(model_id) or COMFYUI_PROVIDER_MAP.get(model_id) or {}
    summary = (meta.get("summary") or "").strip()
    if summary:
        return summary
    return (MODEL_SUMMARY_OVERRIDES.get(model_id) or "").strip()


async def _query_available_models(category: str | None, db: Session) -> dict:
    if category and category not in ("text", "image", "video"):
        raise HTTPException(status_code=400, detail="category 须为 text | image | video")

    query = db.query(RegisteredModel).filter(RegisteredModel.enabled.is_(True))
    if category:
        query = query.filter(RegisteredModel.category == category)
    rows = query.order_by(RegisteredModel.created_at.desc()).all()

    output = []
    for row in rows:
        available = await check_registered_model_available(
            {
                "id": row.id,
                "type": getattr(row, "type", None),
                "api_key": row.api_key,
                "comfyui_file": row.comfyui_file,
            }
        )
        if not available:
            continue
        output.append(
            {
                "id": row.id,
                "display_name": row.display_name,
                "category": row.category,
                "type": row.type,
                "summary": _model_summary(row.id),
            }
        )
    return {"models": output}


@router.get("")
async def list_models(
    category: str | None = Query(None, description="text | image | video"),
    _: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    return await _query_available_models(category, db)


@router.get("/canvas")
async def list_models_legacy(
    category: str | None = Query(None, description="text | image | video"),
    _: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    return await _query_available_models(category, db)


@router.get("/current")
async def get_current_models(_: User = Depends(get_current_user)):
    return comfyui.get_active_models()


@router.get("/{model_id}/capabilities")
async def get_model_capabilities(
    model_id: str,
    _: User = Depends(get_current_user),
):
    """返回模型在注册表中声明的能力（宽高比、分辨率、步数等）。"""
    model = MODEL_MAP.get(model_id)
    if not model:
        raise HTTPException(status_code=404, detail="模型不存在")
    caps = dict(model.get("capabilities") or {})
    backend = (model.get("video_backend") or model.get("workflow_type") or "").strip().lower()
    if backend:
        caps["video_backend"] = backend
    return caps


@router.post("/select")
async def select_model(
    body: SelectModelRequest,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    if user.role != "admin":
        if not user_can_use_model(db, user.id, body.type, body.model):
            raise HTTPException(status_code=403, detail="您没有使用该模型的权限")
    try:
        return comfyui.select_model(body.type, body.model)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e
