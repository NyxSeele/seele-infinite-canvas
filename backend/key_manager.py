"""
key_manager.py
API Key 读取：仅从 model_settings 读取，不兜底环境变量直连。
"""

from sqlalchemy.orm import Session

from db.session import SessionLocal

from services.api_key_service import get_model_setting_api_key


def get_dashscope_api_key(db: Session | None = None) -> str | None:
    """已废弃直连路径：仅读 model_settings 中 qwen-plus 行（若存在）。"""
    return get_api_key("qwen-plus", db)


def get_api_key(model_id: str, db: Session | None = None) -> str | None:
    """获取 model_settings 中指定模型的 API Key；无则返回 None。"""
    own_session = db is None
    if own_session:
        db = SessionLocal()
    try:
        return get_model_setting_api_key(db, model_id)
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
