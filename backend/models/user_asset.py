from datetime import datetime, timezone
from uuid import uuid4

from sqlalchemy import DateTime, ForeignKey, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from db.base import Base


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


def new_asset_id() -> str:
    return str(uuid4())


class UserAsset(Base):
    """用户全局资产库（跨画布）：人物/场景/道具等设定图与常用素材。"""

    __tablename__ = "user_assets"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True)
    team_id: Mapped[str | None] = mapped_column(
        String(36), ForeignKey("teams.id"), index=True, nullable=True
    )
    name: Mapped[str] = mapped_column(String(128))
    kind: Mapped[str] = mapped_column(String(32), default="other", index=True)
    image_url: Mapped[str] = mapped_column(String(1024))
    note: Mapped[str | None] = mapped_column(Text, nullable=True)
    source_canvas_id: Mapped[str | None] = mapped_column(String(64), nullable=True, index=True)
    source_canvas_name: Mapped[str | None] = mapped_column(String(256), nullable=True)
    source_node_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, onupdate=utcnow
    )
