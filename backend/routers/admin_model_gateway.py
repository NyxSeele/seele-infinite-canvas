"""Admin Model Gateway API（挂载于 admin_models 模块）。"""

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, ConfigDict
from sqlalchemy.orm import Session

from core.dependencies import require_admin
from db.session import get_db
from models import User
from services.model_gateway_resolver import (
    get_gateway_api_key,
    get_model_gateway_settings,
    save_model_gateway_settings,
)
from services.registered_model_utils import normalize_openai_compatible_base, resolve_api_model_name

from routers.admin_models import _test_openai_compatible

gateway_router = APIRouter(prefix="/api/admin/model-gateway", tags=["admin-model-gateway"])


class ModelGatewayUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    enabled: bool = False
    base_url: str | None = None
    default_model: str | None = None
    api_key: str | None = None
    clear_api_key: bool = False


class ModelGatewayTestBody(BaseModel):
    model_config = ConfigDict(extra="forbid")

    base_url: str | None = None
    api_key: str | None = None
    default_model: str | None = None


@gateway_router.get("")
async def admin_get_model_gateway(
    _: User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    return get_model_gateway_settings(db)


@gateway_router.put("")
async def admin_put_model_gateway(
    body: ModelGatewayUpdate,
    _: User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    if body.enabled:
        base = (body.base_url or "").strip()
        if not base:
            raise HTTPException(status_code=400, detail="启用网关时 base_url 必填")
        has_key = bool((body.api_key or "").strip())
        if not has_key and not body.clear_api_key:
            existing = get_gateway_api_key(db)
            if not existing:
                raise HTTPException(status_code=400, detail="启用网关时 api_key 必填")
    return save_model_gateway_settings(
        db,
        enabled=body.enabled,
        base_url=body.base_url,
        default_model=body.default_model,
        api_key=body.api_key,
        clear_api_key=body.clear_api_key,
    )


@gateway_router.post("/test-connection")
async def admin_test_model_gateway(
    body: ModelGatewayTestBody,
    _: User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    base_url = (body.base_url or "").strip()
    api_key = (body.api_key or "").strip() or (get_gateway_api_key(db) or "")
    model = (body.default_model or "").strip() or "gpt-4o-mini"

    if not base_url:
        stored = get_model_gateway_settings(db)
        base_url = (stored.get("base_url") or "").strip()
    if not api_key:
        api_key = get_gateway_api_key(db) or ""

    if not base_url:
        return {"ok": False, "latency_ms": None, "error": "Base URL 未配置"}
    if not api_key:
        return {"ok": False, "latency_ms": None, "error": "API Key 未配置"}

    normalized = normalize_openai_compatible_base(base_url)
    ok, latency_ms, error = await _test_openai_compatible(
        api_base=normalized,
        api_key=api_key,
        model_string=resolve_api_model_name(model, model),
    )
    return {"ok": ok, "latency_ms": latency_ms, "error": error}
