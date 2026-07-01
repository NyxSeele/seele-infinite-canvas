from datetime import datetime

from sqlalchemy import Boolean, Column, DateTime, Float, String, Text

from db.base import Base


class RegisteredModel(Base):
    __tablename__ = "registered_models"

    id = Column(String, primary_key=True, index=True)
    display_name = Column(String, nullable=False)
    category = Column(String, nullable=False)  # text | image | video
    type = Column(String, nullable=False)  # api | local
    provider = Column(String, nullable=True)
    api_base = Column(Text, nullable=True)
    api_key = Column(Text, nullable=True)  # TODO: 后续改为加密存储
    model_string = Column(String, nullable=True)
    comfyui_file = Column(String, nullable=True)
    enabled = Column(Boolean, nullable=False, default=False)
    is_default_text = Column(Boolean, nullable=False, default=False)
    input_price_per_million = Column(Float, nullable=True)
    created_at = Column(DateTime, nullable=False, default=datetime.utcnow)
    updated_at = Column(DateTime, nullable=False, default=datetime.utcnow, onupdate=datetime.utcnow)
