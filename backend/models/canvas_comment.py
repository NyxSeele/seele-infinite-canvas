import uuid
from datetime import datetime, timezone

from sqlalchemy import DateTime, ForeignKey, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from db.base import Base


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


def new_comment_id() -> str:
    return str(uuid.uuid4())


class CanvasCommentThread(Base):
    __tablename__ = "canvas_comment_threads"
    __table_args__ = (
        UniqueConstraint("project_id", "node_id", name="uq_canvas_comment_thread_node"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    project_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("canvas_projects.id"), nullable=False, index=True
    )
    node_id: Mapped[str] = mapped_column(String(128), nullable=False, index=True)
    created_by: Mapped[int] = mapped_column(Integer, ForeignKey("users.id"), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, nullable=False
    )


class CanvasCommentMessage(Base):
    __tablename__ = "canvas_comment_messages"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    thread_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("canvas_comment_threads.id"), nullable=False, index=True
    )
    author_id: Mapped[int] = mapped_column(Integer, ForeignKey("users.id"), nullable=False)
    author_name: Mapped[str] = mapped_column(String(128), nullable=False)
    body: Mapped[str] = mapped_column(String(200), nullable=False)
    mentioned_user_ids: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, nullable=False
    )
    updated_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
