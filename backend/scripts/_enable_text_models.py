#!/usr/bin/env python3
"""将 model_registry 中的 text/api 模型写入 registered_models 并启用（一次性运维脚本）。"""
from __future__ import annotations

import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from db.session import SessionLocal
from model_registry import ALL_MODELS
from models import RegisteredModel
from services.api_key_service import encrypt_api_key


def _clear_default_text_flags(db, *, except_id: str | None = None) -> None:
    q = db.query(RegisteredModel).filter(RegisteredModel.is_default_text.is_(True))
    if except_id:
        q = q.filter(RegisteredModel.id != except_id)
    q.update({RegisteredModel.is_default_text: False}, synchronize_session=False)


def main() -> int:
    db = SessionLocal()
    try:
        for preset in ALL_MODELS:
            if preset.get("category") != "text" or preset.get("type") != "api":
                continue

            mid = preset["id"]
            env_name = preset.get("api_key_env") or ""
            env_key = (os.environ.get(env_name) or "").strip() if env_name else ""
            has_key = bool(env_key)
            enabled = has_key
            is_default = mid == "qwen-plus" and enabled

            row = db.get(RegisteredModel, mid)
            if row:
                row.display_name = preset.get("name") or mid
                row.category = "text"
                row.type = "api"
                row.provider = preset.get("provider")
                row.api_base = preset.get("api_base")
                row.model_string = mid
                row.enabled = enabled
                if env_key:
                    row.api_key = encrypt_api_key(env_key)
                if is_default:
                    _clear_default_text_flags(db, except_id=mid)
                    row.is_default_text = True
                elif row.is_default_text:
                    row.is_default_text = False
                print(f"updated {mid} enabled={enabled} default={row.is_default_text}")
            else:
                if is_default:
                    _clear_default_text_flags(db)
                db.add(
                    RegisteredModel(
                        id=mid,
                        display_name=preset.get("name") or mid,
                        category="text",
                        type="api",
                        provider=preset.get("provider"),
                        api_base=preset.get("api_base"),
                        api_key=encrypt_api_key(env_key) if env_key else None,
                        model_string=mid,
                        enabled=enabled,
                        is_default_text=is_default,
                    )
                )
                print(f"inserted {mid} enabled={enabled} default={is_default}")
        db.commit()
    finally:
        db.close()
    print("OK")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
