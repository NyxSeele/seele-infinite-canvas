from pathlib import Path
from uuid import uuid4

from fastapi import APIRouter, Depends, File, Form, HTTPException, Query, UploadFile
from sqlalchemy.orm import Session

from core.dependencies import get_current_user
from db.session import get_db
from models import User
from models.team import Team
from models.user_asset import UserAsset, new_asset_id
from models.user_upload import UserUpload
from schemas.assets import AssetCreate, AssetOut, AssetUpdate
from services.media_access import (
    append_media_ticket,
    assert_user_can_read_upload_url,
    issue_media_ticket,
)
from services.team_service import EDIT_ROLES, get_member_role, require_team_editor
from services.upload_validation import suffix_for_mime, validate_image_upload

router = APIRouter(prefix="/api/assets", tags=["assets"])

UPLOAD_DIR = Path("uploads/images")
UPLOAD_DIR.mkdir(parents=True, exist_ok=True)
ALLOWED_TYPES = {"image/jpeg", "image/png", "image/webp", "image/gif"}
MAX_SIZE = 10 * 1024 * 1024


def _to_out(
    row: UserAsset,
    ticket: str,
    owner: User | None = None,
    team_name: str | None = None,
) -> AssetOut:
    return AssetOut(
        id=row.id,
        name=row.name,
        kind=row.kind,
        image_url=append_media_ticket(row.image_url, ticket),
        note=row.note,
        source_canvas_id=row.source_canvas_id,
        source_canvas_name=row.source_canvas_name,
        source_node_id=row.source_node_id,
        team_id=row.team_id,
        team_name=team_name,
        owner_id=row.user_id,
        owner_name=owner.username if owner else None,
        created_at=row.created_at,
        updated_at=row.updated_at,
    )


def _resolve_team_scope(db: Session, user: User, team_id: str | None) -> str | None:
    if not team_id:
        return None
    role = get_member_role(db, team_id, user.id)
    if not role:
        raise HTTPException(status_code=403, detail="无权访问该团队资产")
    return team_id


@router.get("", response_model=list[AssetOut])
def list_assets(
    kind: str | None = None,
    source_canvas_id: str | None = None,
    team_id: str | None = Query(default=None),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    ticket = issue_media_ticket(current_user.id)["media_ticket"]
    scoped_team = _resolve_team_scope(db, current_user, team_id)

    if scoped_team:
        q = (
            db.query(UserAsset, User, Team)
            .join(User, User.id == UserAsset.user_id)
            .outerjoin(Team, Team.id == UserAsset.team_id)
            .filter(UserAsset.team_id == scoped_team)
        )
        if kind:
            q = q.filter(UserAsset.kind == kind)
        if source_canvas_id:
            q = q.filter(UserAsset.source_canvas_id == source_canvas_id)
        rows = q.order_by(UserAsset.updated_at.desc()).all()
        return [_to_out(asset, ticket, owner, team.name if team else None) for asset, owner, team in rows]

    q = db.query(UserAsset).filter(
        UserAsset.user_id == current_user.id,
        UserAsset.team_id.is_(None),
    )
    if kind:
        q = q.filter(UserAsset.kind == kind)
    if source_canvas_id:
        q = q.filter(UserAsset.source_canvas_id == source_canvas_id)
    rows = q.order_by(UserAsset.updated_at.desc()).all()
    return [_to_out(r, ticket, current_user) for r in rows]


@router.post("", response_model=AssetOut)
def create_asset(
    body: AssetCreate,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    if body.team_id:
        require_team_editor(db, body.team_id, current_user)
    image_url = body.image_url.strip()
    if image_url:
        assert_user_can_read_upload_url(db, current_user, image_url)
    team = db.get(Team, body.team_id) if body.team_id else None
    row = UserAsset(
        id=new_asset_id(),
        user_id=current_user.id,
        team_id=body.team_id,
        name=body.name.strip(),
        kind=body.kind or "other",
        image_url=image_url,
        note=(body.note or "").strip() or None,
        source_canvas_id=(body.source_canvas_id or "").strip() or None,
        source_canvas_name=(body.source_canvas_name or "").strip() or None,
        source_node_id=(body.source_node_id or "").strip() or None,
    )
    db.add(row)
    db.commit()
    db.refresh(row)
    ticket = issue_media_ticket(current_user.id)["media_ticket"]
    return _to_out(row, ticket, current_user, team.name if team else None)


@router.post("/upload", response_model=AssetOut)
async def upload_asset(
    file: UploadFile = File(...),
    name: str = Form(...),
    kind: str = Form("other"),
    note: str | None = Form(None),
    source_canvas_id: str | None = Form(None),
    source_canvas_name: str | None = Form(None),
    source_node_id: str | None = Form(None),
    team_id: str | None = Form(None),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    if team_id:
        require_team_editor(db, team_id, current_user)
    if file.content_type not in ALLOWED_TYPES:
        raise HTTPException(status_code=400, detail="不支持的图片格式")

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

    trimmed_name = (name or "").strip() or Path(file.filename or "未命名").stem[:128]
    row = UserAsset(
        id=new_asset_id(),
        user_id=current_user.id,
        team_id=team_id or None,
        name=trimmed_name,
        kind=kind if kind in ("character", "scene", "prop", "other") else "other",
        image_url=f"/api/uploads/{rel_path}",
        note=(note or "").strip() or None,
        source_canvas_id=(source_canvas_id or "").strip() or None,
        source_canvas_name=(source_canvas_name or "").strip() or None,
        source_node_id=(source_node_id or "").strip() or None,
    )
    db.add(row)
    db.commit()
    db.refresh(row)
    team = db.get(Team, team_id) if team_id else None
    ticket = issue_media_ticket(current_user.id)["media_ticket"]
    return _to_out(row, ticket, current_user, team.name if team else None)


@router.patch("/{asset_id}", response_model=AssetOut)
def update_asset(
    asset_id: str,
    body: AssetUpdate,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    row = db.query(UserAsset).filter(UserAsset.id == asset_id).first()
    if not row:
        raise HTTPException(status_code=404, detail="资产不存在")
    if row.team_id:
        role = get_member_role(db, row.team_id, current_user.id)
        if role not in EDIT_ROLES or row.user_id != current_user.id:
            if role not in ("owner", "admin"):
                raise HTTPException(status_code=403, detail="无权修改该资产")
    elif row.user_id != current_user.id:
        raise HTTPException(status_code=404, detail="资产不存在")

    if body.name is not None:
        row.name = body.name.strip()
    if body.kind is not None:
        row.kind = body.kind
    if body.image_url is not None:
        row.image_url = body.image_url.strip()
    if body.note is not None:
        row.note = body.note.strip() or None
    if body.source_canvas_id is not None:
        row.source_canvas_id = body.source_canvas_id.strip() or None
    if body.source_canvas_name is not None:
        row.source_canvas_name = body.source_canvas_name.strip() or None
    if body.source_node_id is not None:
        row.source_node_id = body.source_node_id.strip() or None
    if body.team_id is not None:
        if body.team_id:
            require_team_editor(db, body.team_id, current_user)
        row.team_id = body.team_id or None

    db.commit()
    db.refresh(row)
    team = db.get(Team, row.team_id) if row.team_id else None
    owner = db.get(User, row.user_id)
    ticket = issue_media_ticket(current_user.id)["media_ticket"]
    return _to_out(row, ticket, owner, team.name if team else None)


@router.delete("/{asset_id}")
def delete_asset(
    asset_id: str,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    row = db.query(UserAsset).filter(UserAsset.id == asset_id).first()
    if not row:
        raise HTTPException(status_code=404, detail="资产不存在")
    if row.team_id:
        role = get_member_role(db, row.team_id, current_user.id)
        if role not in ("owner", "admin") and row.user_id != current_user.id:
            raise HTTPException(status_code=403, detail="无权删除该资产")
    elif row.user_id != current_user.id:
        raise HTTPException(status_code=404, detail="资产不存在")
    db.delete(row)
    db.commit()
    return {"ok": True}
