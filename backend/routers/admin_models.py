import asyncio
import re
import time
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException
from openai import AsyncOpenAI
from pydantic import BaseModel, ConfigDict
from sqlalchemy.orm import Session

from core.dependencies import require_admin
from db.session import get_db
from model_checker import check_registered_model_available, clear_cache
from models import RegisteredModel, User
from core.secret_store import mask_secret
from services.api_key_service import encrypt_api_key, get_registered_model_api_key
from services.local_model_sync import sync_local_models
from services.llm_router import (
    get_usage_24h,
    list_routing_snapshot,
    set_default_text_model,
    set_routing_mode,
)
from services.registered_model_utils import (
    MODEL_ID_INVALID_MSG,
    MODEL_ID_RE,
    normalize_openai_compatible_base,
    resolve_api_model_name,
    slugify_model_id,
)

router = APIRouter(prefix="/api/admin/models", tags=["admin-models"])


def _row_value(row: RegisteredModel, attr: str):
    """避免 ORM 列名 type 等与内置属性冲突，统一从 mapper 取值。"""
    return getattr(row, attr)


def _serialize_model(row: RegisteredModel, available: bool) -> dict:
    model_id = _row_value(row, "id")
    return {
        "id": model_id,
        "display_name": _row_value(row, "display_name") or model_id or "",
        "category": _row_value(row, "category") or "",
        "type": _row_value(row, "type") or "",
        "provider": _row_value(row, "provider"),
        "api_base": _row_value(row, "api_base"),
        "model_string": _row_value(row, "model_string"),
        "api_model_name": resolve_api_model_name(
            model_id, _row_value(row, "model_string"), display_name=_row_value(row, "display_name")
        ),
        "comfyui_file": _row_value(row, "comfyui_file"),
        "enabled": bool(_row_value(row, "enabled")),
        "is_default_text": bool(_row_value(row, "is_default_text")),
        "input_price_per_million": _row_value(row, "input_price_per_million"),
        "usage_24h_tokens": get_usage_24h(model_id),
        "available": available,
        "api_key_masked": mask_secret(_row_value(row, "api_key")),
    }


class RegisteredModelCreate(BaseModel):
    id: str
    display_name: str
    category: Literal["text", "image", "video"]
    type: Literal["api", "local"]
    provider: str | None = None
    api_base: str | None = None
    api_key: str | None = None
    model_string: str | None = None
    api_model_name: str | None = None
    comfyui_file: str | None = None
    enabled: bool = False
    is_default_text: bool | None = None
    input_price_per_million: float | None = None


class RegisteredModelUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    display_name: str | None = None
    category: Literal["text", "image", "video"] | None = None
    type: Literal["api", "local"] | None = None
    provider: str | None = None
    api_base: str | None = None
    api_key: str | None = None
    model_string: str | None = None
    api_model_name: str | None = None
    comfyui_file: str | None = None
    enabled: bool | None = None
    is_default_text: bool | None = None
    input_price_per_million: float | None = None


class LlmRoutingUpdate(BaseModel):
    mode: Literal["fixed", "cheapest", "balanced"]


def _validate_payload(data: dict, is_create: bool) -> None:
    model_type = data.get("type")
    if is_create and model_type is None:
        raise HTTPException(status_code=400, detail="type 必填")
    if model_type == "api":
        if not (data.get("api_base") or "").strip():
            raise HTTPException(status_code=400, detail="type=api 时 api_base 必填")
    if model_type == "local":
        comfyui_file = data.get("comfyui_file")
        if comfyui_file is not None and not comfyui_file.strip():
            raise HTTPException(status_code=400, detail="comfyui_file 不能为空字符串")


async def _test_openai_compatible(
    api_base: str,
    api_key: str,
    model_string: str,
) -> tuple[bool, int | None, str | None]:
    normalized_base = normalize_openai_compatible_base(api_base)
    client = AsyncOpenAI(api_key=api_key, base_url=normalized_base)
    begin = time.perf_counter()
    try:
        await asyncio.wait_for(
            client.chat.completions.create(
                model=model_string,
                messages=[{"role": "user", "content": "hi"}],
                max_tokens=1,
            ),
            timeout=10.0,
        )
        return True, int((time.perf_counter() - begin) * 1000), None
    except asyncio.TimeoutError:
        return False, None, "连接超时"
    except Exception as e:
        err = str(e)
        if "404" in err or "not found" in err.lower() or "NotFound" in err:
            err = (
                f"模型未找到（调用名: {model_string}）。"
                "请确认「模型调用名」与平台文档一致。"
            )
            if normalized_base != api_base.strip().rstrip("/"):
                err += f" 已尝试兼容地址: {normalized_base}"
            elif "maas.aliyuncs.com" in api_base.lower() and "/api/v1" in api_base:
                err += (
                    " 百炼专属端点请改用 OpenAI 兼容路径："
                    f"{normalize_openai_compatible_base(api_base)}"
                )
        return False, None, err


@router.get("")
async def admin_list_models(
    _: User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    rows = db.query(RegisteredModel).order_by(RegisteredModel.created_at.desc()).all()
    payload = []
    for row in rows:
        available = await check_registered_model_available(
            {
                "id": _row_value(row, "id"),
                "type": _row_value(row, "type"),
                "api_key": get_registered_model_api_key(row),
                "comfyui_file": _row_value(row, "comfyui_file"),
            }
        )
        payload.append(_serialize_model(row, available))
    return {"models": payload}


@router.post("")
async def admin_create_model(
    body: RegisteredModelCreate,
    _: User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    model_id = body.id.strip()
    official_from_id: str | None = None
    if model_id and not MODEL_ID_RE.match(model_id):
        official_from_id = model_id
        model_id = slugify_model_id(model_id)
    if not model_id or not MODEL_ID_RE.match(model_id):
        raise HTTPException(status_code=400, detail=MODEL_ID_INVALID_MSG)
    if db.get(RegisteredModel, model_id):
        raise HTTPException(status_code=400, detail="模型 ID 已存在")
    if body.type == "local":
        raise HTTPException(
            status_code=400,
            detail="本地模型由 ComfyUI 自动识别，请使用「刷新检测」同步",
        )

    data = body.model_dump()
    _validate_payload(data, is_create=True)
    row = RegisteredModel(
        id=model_id,
        display_name=body.display_name.strip(),
        category=body.category,
        type=body.type,
        provider=(body.provider or "").strip() or None,
        api_base=normalize_openai_compatible_base((body.api_base or "").strip()) or None,
        api_key=encrypt_api_key((body.api_key or "").strip() or None),
        model_string=resolve_api_model_name(
            model_id,
            body.api_model_name or body.model_string or official_from_id,
            display_name=body.display_name,
        ),
        comfyui_file=(body.comfyui_file or "").strip() or None,
        enabled=bool(body.enabled),
        is_default_text=bool(body.is_default_text),
        input_price_per_million=body.input_price_per_million,
    )
    db.add(row)
    db.commit()
    db.refresh(row)
    clear_cache(model_id)
    available = await check_registered_model_available(
        {
            "id": _row_value(row, "id"),
            "type": _row_value(row, "type"),
            "api_key": _row_value(row, "api_key"),
            "comfyui_file": _row_value(row, "comfyui_file"),
        }
    )
    return _serialize_model(row, available)


@router.post("/refresh-check")
async def admin_refresh_check(_: User = Depends(require_admin)):
    clear_cache()
    inserted = await sync_local_models()
    return {"cleared": True, "synced": True, "inserted": inserted}


@router.get("/llm-routing")
async def admin_get_llm_routing(
    _: User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    return list_routing_snapshot(db)


@router.put("/llm-routing")
async def admin_put_llm_routing(
    body: LlmRoutingUpdate,
    _: User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    try:
        mode = set_routing_mode(body.mode, db)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    snapshot = list_routing_snapshot(db)
    snapshot["mode"] = mode
    return snapshot


@router.put("/{model_id}")
async def admin_update_model(
    model_id: str,
    body: RegisteredModelUpdate,
    _: User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    row = db.get(RegisteredModel, model_id)
    if not row:
        raise HTTPException(status_code=404, detail=f"模型不存在: {model_id}")

    updates = body.model_dump(exclude_unset=True)
    if not updates:
        available = await check_registered_model_available(
            {
                "id": _row_value(row, "id"),
                "type": _row_value(row, "type"),
                "api_key": get_registered_model_api_key(row),
                "comfyui_file": _row_value(row, "comfyui_file"),
            }
        )
        return _serialize_model(row, available)

    if "type" in updates or "api_base" in updates or "comfyui_file" in updates:
        merged = {
            "type": updates.get("type", _row_value(row, "type")),
            "api_base": updates.get("api_base", row.api_base),
            "comfyui_file": updates.get("comfyui_file", row.comfyui_file),
        }
        _validate_payload(merged, is_create=False)

    if "api_model_name" in updates or "model_string" in updates or "display_name" in updates:
        row.model_string = resolve_api_model_name(
            model_id,
            updates.get("api_model_name", updates.get("model_string", row.model_string)),
            display_name=updates.get("display_name", row.display_name),
        )
        updates.pop("api_model_name", None)
        updates.pop("model_string", None)

    for key, val in updates.items():
        if key == "api_key":
            val = encrypt_api_key(val.strip() if isinstance(val, str) and val.strip() else None)
        elif key == "api_base" and isinstance(val, str):
            val = normalize_openai_compatible_base(val.strip()) or None
        elif key == "is_default_text" and val:
            db.query(RegisteredModel).filter(RegisteredModel.is_default_text.is_(True)).update(
                {RegisteredModel.is_default_text: False},
                synchronize_session=False,
            )
        elif isinstance(val, str):
            val = val.strip() or None
        setattr(row, key, val)

    db.commit()
    db.refresh(row)
    clear_cache(model_id)
    available = await check_registered_model_available(
        {
            "id": _row_value(row, "id"),
            "type": _row_value(row, "type"),
            "api_key": _row_value(row, "api_key"),
            "comfyui_file": _row_value(row, "comfyui_file"),
        }
    )
    return _serialize_model(row, available)


@router.delete("/{model_id}")
async def admin_delete_model(
    model_id: str,
    _: User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    row = db.get(RegisteredModel, model_id)
    if not row:
        raise HTTPException(status_code=404, detail=f"模型不存在: {model_id}")
    db.delete(row)
    db.commit()
    clear_cache(model_id)
    return {"deleted": True, "model_id": model_id}


@router.post("/{model_id}/test-connection")
async def admin_test_connection(
    model_id: str,
    _: User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    row = db.get(RegisteredModel, model_id)
    if not row:
        raise HTTPException(status_code=404, detail=f"模型不存在: {model_id}")
    if row.type != "api":
        raise HTTPException(status_code=400, detail="仅 API 类型模型支持测试连接")
    api_key = get_registered_model_api_key(row)
    if not api_key:
        return {"ok": False, "latency_ms": None, "error": "API Key 未配置"}
    if not (row.api_base or "").strip():
        return {"ok": False, "latency_ms": None, "error": "API Base 未配置"}

    ok, latency_ms, error = await _test_openai_compatible(
        api_base=row.api_base,
        api_key=api_key,
        model_string=resolve_api_model_name(
            model_id, row.model_string, display_name=row.display_name
        ),
    )
    return {"ok": ok, "latency_ms": latency_ms, "error": error}


@router.post("/{model_id}/set-default-text")
async def admin_set_default_text_model(
    model_id: str,
    _: User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    row = db.get(RegisteredModel, model_id)
    if not row:
        raise HTTPException(status_code=404, detail=f"模型不存在: {model_id}")
    try:
        row = set_default_text_model(model_id, db)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    available = await check_registered_model_available(
        {
            "id": _row_value(row, "id"),
            "type": _row_value(row, "type"),
            "api_key": get_registered_model_api_key(row),
            "comfyui_file": _row_value(row, "comfyui_file"),
        }
    )
    return _serialize_model(row, available)
