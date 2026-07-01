import os
from pathlib import Path
from uuid import uuid4

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile
from sqlalchemy.orm import Session

from core.dependencies import get_current_user
from db.session import get_db
from models import User
from models.user_upload import UserUpload
from services.media_access import append_media_ticket, issue_media_ticket
from services.upload_validation import suffix_for_mime, validate_image_upload

router = APIRouter(prefix="/api/upload", tags=["upload"])

UPLOAD_DIR = Path("uploads/images")
UPLOAD_DIR.mkdir(parents=True, exist_ok=True)

ALLOWED_TYPES = {"image/jpeg", "image/png", "image/webp", "image/gif"}
MAX_SIZE = 10 * 1024 * 1024  # 10 MB


@router.post("/image")
async def upload_image(
    file: UploadFile = File(...),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    if file.content_type not in ALLOWED_TYPES:
        raise HTTPException(status_code=400, detail="不支持的图片格式，仅允许 JPG / PNG / WebP / GIF")

    content = await file.read()
    mime = validate_image_upload(content, file.content_type)

    suffix = suffix_for_mime(mime, Path(file.filename or "image.jpg").suffix or ".jpg")
    if suffix.lower() not in (".jpg", ".jpeg", ".png", ".webp", ".gif"):
        suffix = ".jpg"
    filename = f"{uuid4()}{suffix}"
    save_path = UPLOAD_DIR / filename

    with open(save_path, "wb") as f:
        f.write(content)

    rel_path = f"images/{filename}"
    db.add(UserUpload(user_id=current_user.id, path=rel_path))
    db.commit()

    ticket = issue_media_ticket(current_user.id)["media_ticket"]
    path = append_media_ticket(f"/api/uploads/{rel_path}", ticket)
    return {"url": path, "filename": filename, "media_ticket": ticket}
