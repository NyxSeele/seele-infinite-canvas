import uuid
from datetime import datetime, timezone

from sqlalchemy import DateTime, ForeignKey, Integer, String, Text, text
from sqlalchemy.orm import Mapped, mapped_column

from db.base import Base


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


def new_project_id() -> str:
    return str(uuid.uuid4())


class CanvasProject(Base):
    __tablename__ = "canvas_projects"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    user_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("users.id"), nullable=False, index=True
    )
    team_id: Mapped[str | None] = mapped_column(
        String(36), ForeignKey("teams.id"), nullable=True, index=True
    )
    version: Mapped[int] = mapped_column(Integer, nullable=False, server_default=text("1"))
    name: Mapped[str] = mapped_column(String(256), nullable=False, default="未命名画布")
    data: Mapped[str] = mapped_column(Text, nullable=False, default='{"nodes":[],"edges":[]}')
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, onupdate=utcnow, nullable=False
    )
    last_modified_by: Mapped[str | None] = mapped_column(String(64), nullable=True)
