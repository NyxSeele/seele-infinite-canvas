from datetime import datetime, timezone

from sqlalchemy import DateTime, Float, ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from db.base import Base


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


class Task(Base):
    __tablename__ = "tasks"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    user_id: Mapped[int | None] = mapped_column(
        ForeignKey("users.id"), index=True, nullable=True
    )
    team_id: Mapped[str | None] = mapped_column(
        String(36), ForeignKey("teams.id"), index=True, nullable=True
    )
    task_type: Mapped[str] = mapped_column(String(20))
    status: Mapped[str] = mapped_column(String(20), default="pending")
    prompt_text: Mapped[str | None] = mapped_column(Text, nullable=True)
    result: Mapped[str | None] = mapped_column(Text, nullable=True)
    error: Mapped[str | None] = mapped_column(Text, nullable=True)
    comfyui_prompt_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    comfyui_node_url: Mapped[str | None] = mapped_column(String(256), nullable=True)
    node_id: Mapped[str | None] = mapped_column(String(128), nullable=True)
    lut_applied: Mapped[bool] = mapped_column(default=False)
    sound_note: Mapped[str | None] = mapped_column(Text, nullable=True)
    model_id: Mapped[str | None] = mapped_column(String(64), nullable=True, index=True)
    video_backend: Mapped[str | None] = mapped_column(String(32), nullable=True)
    use_reactor: Mapped[bool] = mapped_column(default=False)
    reactor_face_image: Mapped[str | None] = mapped_column(Text, nullable=True)
    user_rating: Mapped[int | None] = mapped_column(Integer, nullable=True)
    rating_tags: Mapped[str | None] = mapped_column(Text, nullable=True)
    rated_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    original_input: Mapped[str | None] = mapped_column(Text, nullable=True)
    compiled_prompt: Mapped[str | None] = mapped_column(Text, nullable=True)
    rating_comment: Mapped[str | None] = mapped_column(Text, nullable=True)
    generation_params: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    completed_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    generation_seconds: Mapped[float | None] = mapped_column(Float, nullable=True)

    user: Mapped["User | None"] = relationship("User", back_populates="tasks")
