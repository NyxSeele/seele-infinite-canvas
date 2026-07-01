from pathlib import Path

from fastapi import HTTPException
from sqlalchemy.orm import Session

from comfyui import client as comfyui
from models import RegisteredModel, User, UserModelPermission
from models.model_permission import utcnow

MODEL_CONFIG_PATH = comfyui.MODEL_CONFIG_PATH


def _display_name(model_id: str) -> str:
    dot = model_id.rfind(".")
    return model_id[:dot] if dot > 0 else model_id


def list_catalog_models(db: Session | None = None) -> list[dict]:
    """从 model_config.json、ComfyUI 扫描与 registered_models 构建模型目录。"""
    if not MODEL_CONFIG_PATH.is_file():
        raise HTTPException(status_code=500, detail="model_config.json 不存在")

    try:
        config = comfyui.load_model_config(MODEL_CONFIG_PATH)
    except Exception as exc:
        raise HTTPException(
            status_code=500, detail=f"读取 model_config.json 失败: {exc}"
        ) from exc

    catalog: list[dict] = []
    seen: set[str] = set()

    if isinstance(config.get("models"), list):
        for item in config["models"]:
            if not isinstance(item, dict):
                continue
            model_id = (item.get("id") or item.get("model_id") or "").strip()
            if not model_id or model_id in seen:
                continue
            model_type = (item.get("type") or "image").strip().lower()
            if model_type not in ("image", "video", "text"):
                model_type = "image"
            catalog.append(
                {
                    "model_id": model_id,
                    "name": (item.get("name") or _display_name(model_id)).strip(),
                    "type": model_type,
                }
            )
            seen.add(model_id)

    for model_type in ("image", "video"):
        for model_id in comfyui.get_checkpoints_by_type(model_type):
            if model_id in seen:
                continue
            catalog.append(
                {
                    "model_id": model_id,
                    "name": _display_name(model_id),
                    "type": model_type,
                }
            )
            seen.add(model_id)

    for key, model_type in (("image_model", "image"), ("video_model", "video")):
        model_id = (config.get(key) or "").strip()
        if model_id and model_id not in seen:
            catalog.append(
                {
                    "model_id": model_id,
                    "name": _display_name(model_id),
                    "type": model_type,
                }
            )
            seen.add(model_id)

    if db is not None:
        text_rows = (
            db.query(RegisteredModel)
            .filter(RegisteredModel.category == "text")
            .order_by(RegisteredModel.display_name)
            .all()
        )
        for row in text_rows:
            if row.id in seen:
                continue
            catalog.append(
                {
                    "model_id": row.id,
                    "name": row.display_name or row.id,
                    "type": "text",
                }
            )
            seen.add(row.id)

    catalog.sort(key=lambda m: (m["type"], m["name"].lower()))
    return catalog


def _ensure_user(db: Session, user_id: int) -> User:
    user = db.get(User, user_id)
    if not user:
        raise HTTPException(status_code=404, detail="用户不存在")
    return user


def get_user_model_permissions(db: Session, user_id: int) -> dict:
    _ensure_user(db, user_id)
    catalog = list_catalog_models(db)
    records = {
        row.model_id: row
        for row in db.query(UserModelPermission)
        .filter(UserModelPermission.user_id == user_id)
        .all()
    }
    permissions = []
    for item in catalog:
        rec = records.get(item["model_id"])
        permissions.append(
            {
                "model_id": item["model_id"],
                "enabled": rec.enabled if rec else True,
            }
        )
    return {"user_id": user_id, "permissions": permissions}


def update_user_model_permissions(
    db: Session, user_id: int, permissions: list[dict]
) -> dict:
    _ensure_user(db, user_id)
    catalog_ids = {m["model_id"] for m in list_catalog_models(db)}
    now = utcnow()

    for item in permissions:
        model_id = (item.get("model_id") or "").strip()
        if not model_id:
            raise HTTPException(status_code=400, detail="model_id 不能为空")
        if model_id not in catalog_ids:
            raise HTTPException(
                status_code=400, detail=f"未知模型: {model_id}"
            )
        enabled = bool(item.get("enabled", True))
        row = (
            db.query(UserModelPermission)
            .filter(
                UserModelPermission.user_id == user_id,
                UserModelPermission.model_id == model_id,
            )
            .first()
        )
        if row:
            row.enabled = enabled
            row.updated_at = now
        else:
            db.add(
                UserModelPermission(
                    user_id=user_id,
                    model_id=model_id,
                    enabled=enabled,
                )
            )

    db.commit()
    return get_user_model_permissions(db, user_id)


def get_enabled_models_for_user(db: Session, user_id: int) -> dict:
    data = get_user_model_permissions(db, user_id)
    catalog = {m["model_id"]: m for m in list_catalog_models(db)}
    models = []
    for perm in data["permissions"]:
        if not perm["enabled"]:
            continue
        meta = catalog.get(perm["model_id"])
        if not meta:
            continue
        models.append(
            {
                "id": perm["model_id"],
                "name": meta["name"],
                "type": meta["type"],
                "enabled": True,
            }
        )
    return {"models": models}


def user_can_use_model(
    db: Session, user_id: int, model_type: str, model_id: str
) -> bool:
    if user_id is None:
        return True
    user = db.get(User, user_id)
    if user and user.role == "admin":
        return True
    perms = get_user_model_permissions(db, user_id)
    for p in perms["permissions"]:
        if p["model_id"] == model_id:
            return p["enabled"]
    return True
