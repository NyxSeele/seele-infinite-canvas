import json
import uuid
from datetime import datetime, timedelta, timezone

from sqlalchemy import DateTime, ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from db.base import Base


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


def new_invite_token() -> str:
    return uuid.uuid4().hex


class TeamInvite(Base):
    __tablename__ = "team_invites"

    token: Mapped[str] = mapped_column(String(64), primary_key=True)
    team_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("teams.id", ondelete="CASCADE"), index=True
    )
    created_by: Mapped[int] = mapped_column(Integer, ForeignKey("users.id"), nullable=False)
    expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    max_uses: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    use_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    settings_json: Mapped[str] = mapped_column(Text, default="{}", nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, nullable=False
    )

    def settings(self) -> dict:
        try:
            return json.loads(self.settings_json or "{}")
        except json.JSONDecodeError:
            return {}

    def set_settings(self, data: dict) -> None:
        self.settings_json = json.dumps(data or {}, ensure_ascii=False)

    def is_expired(self) -> bool:
        if self.expires_at is None:
            return False
        exp = self.expires_at
        if exp.tzinfo is None:
            exp = exp.replace(tzinfo=timezone.utc)
        return utcnow() >= exp

    def is_exhausted(self) -> bool:
        if self.max_uses <= 0:
            return False
        return self.use_count >= self.max_uses
