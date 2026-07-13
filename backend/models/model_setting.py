from datetime import datetime

from sqlalchemy import Boolean, Column, DateTime, String, Text

from db.base import Base


class ModelSetting(Base):
    """
    每个注册模型的管理员开关状态。
    model_id 对应 model_registry.ALL_MODELS 中的 id 字段。
    api_key: 管理员录入的 Key（Fernet 加密存储，见 api_key_service）
    """

    __tablename__ = "model_settings"

    model_id = Column(String, primary_key=True, index=True)
    enabled = Column(Boolean, nullable=False, default=False)
    api_key = Column(Text, nullable=True, default=None)
    updated_at = Column(
        DateTime, nullable=False, default=datetime.utcnow, onupdate=datetime.utcnow
    )
