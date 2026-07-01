from datetime import datetime

from sqlalchemy import Column, DateTime, String, Text

from db.base import Base


class SystemSetting(Base):
    """全局 key-value 配置（Admin 可写）。"""

    __tablename__ = "system_settings"

    key = Column(String(128), primary_key=True)
    value = Column(Text, nullable=True)
    updated_at = Column(
        DateTime, nullable=False, default=datetime.utcnow, onupdate=datetime.utcnow
    )
