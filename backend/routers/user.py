from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from core.dependencies import get_current_user
from db.session import get_db
from models import User
from schemas.user import UserModelsResponse
from services.model_permission_service import get_enabled_models_for_user

router = APIRouter(prefix="/api/user", tags=["user"])


@router.get("/models", response_model=UserModelsResponse)
def get_my_models(
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    return get_enabled_models_for_user(db, user.id)
