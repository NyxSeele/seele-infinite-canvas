"""
key_manager.py
API Key 读取：优先 model_settings.api_key，兜底环境变量。
"""

import os

from sqlalchemy.orm import Session

from db.session import SessionLocal
from models import ModelSetting


from services.api_key_service import get_model_setting_api_key


def get_dashscope_api_key(db: Session | None = None) -> str | None:
    """百炼 / DashScope 统一 API Key（优先 model_settings，兜底 DASHSCOPE_API_KEY）。"""
    return get_api_key("qwen-plus", "DASHSCOPE_API_KEY", db)


def get_api_key(model_id: str, env_var: str, db: Session | None = None) -> str | None:
    """
    获取模型 API Key。
    优先读 model_settings.api_key，兜底读环境变量，都没有返回 None。
    """
    own_session = db is None
    if own_session:
        db = SessionLocal()
    try:
        stored = get_model_setting_api_key(db, model_id)
        if stored:
            return stored
        env_val = os.environ.get(env_var, "").strip()
        return env_val or None
    finally:
        if own_session:
            db.close()


def mask_api_key(key: str | None) -> str | None:
    """脱敏：仅暴露后 4 位，如 ****K7Xp。"""
    if not key:
        return None
    k = key.strip()
    if len(k) <= 4:
        return "****"
    return "****" + k[-4:]
