from datetime import datetime, timezone

from sqlalchemy import DateTime, ForeignKey, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from db.base import Base


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


class ExcelImportLog(Base):
    __tablename__ = "excel_import_log"
    __table_args__ = (
        UniqueConstraint("project_id", "sheet_name", name="uq_excel_import_project_sheet"),
    )

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    project_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("canvas_projects.id"), nullable=False, index=True
    )
    sheet_name: Mapped[str] = mapped_column(String(256), nullable=False)
    content_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    linked_node_id: Mapped[str | None] = mapped_column(String(128), nullable=True)
    last_imported_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, nullable=False
    )
