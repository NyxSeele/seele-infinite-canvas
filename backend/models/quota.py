from datetime import date

from sqlalchemy import Date, ForeignKey, Integer, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from db.base import Base


def first_day_of_month(d: date | None = None) -> date:
    d = d or date.today()
    return d.replace(day=1)


class QuotaPlan(Base):
    __tablename__ = "quota_plans"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(String(50), unique=True)
    image_limit: Mapped[int] = mapped_column(Integer)
    video_limit: Mapped[int] = mapped_column(Integer)


class UserQuota(Base):
    __tablename__ = "user_quotas"
    __table_args__ = (UniqueConstraint("user_id", name="uq_user_quotas_user_id"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True)
    plan_name: Mapped[str] = mapped_column(String(50), default="default")
    image_limit: Mapped[int] = mapped_column(Integer, default=50)
    video_limit: Mapped[int] = mapped_column(Integer, default=10)
    image_used: Mapped[int] = mapped_column(Integer, default=0)
    video_used: Mapped[int] = mapped_column(Integer, default=0)
    period_start: Mapped[date] = mapped_column(Date, default=first_day_of_month)

    user: Mapped["User"] = relationship("User", back_populates="quota")
