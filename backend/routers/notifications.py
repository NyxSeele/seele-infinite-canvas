from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from core.dependencies import get_current_user
from db.session import get_db
from models import User
from services.notification_service import list_notifications, mark_notifications_read

router = APIRouter(prefix="/api/notifications", tags=["notifications"])


class MarkReadRequest(BaseModel):
    notification_ids: list[str] = Field(default_factory=list)
    mark_all: bool = False


@router.get("")
def get_notifications(
    limit: int = Query(default=50, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    return list_notifications(db, user.id, limit=limit, offset=offset)


@router.post("/mark-read")
def post_mark_read(
    body: MarkReadRequest,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    count = mark_notifications_read(
        db,
        user.id,
        notification_ids=body.notification_ids,
        mark_all=body.mark_all,
    )
    return {"ok": True, "marked": count}
