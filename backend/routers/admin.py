from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from core.datetime_utils import to_utc_iso
from core.dependencies import require_admin
from db.session import get_db
from models import Task, User, UserQuota
from schemas.admin import (
    AdminFeedbackAnalysesResponse,
    AdminFeedbackAnalyzeResponse,
    AdminFeedbackRecordsResponse,
    AdminFeedbackStatsResponse,
    AdminFeedbackTrendsResponse,
    AdminModelsListResponse,
    AdminOverviewResponse,
    AdminOverviewStats,
    AdminTaskListResponse,
    UpdateQuotaRequest,
    UpdateRoleRequest,
    UpdateR2AccessRequest,
    UpdateStatusRequest,
    UpdateUserModelPermissionsRequest,
    UserDetailResponse,
    UserListResponse,
    UserModelPermissionsResponse,
)
from services.feedback_service import (
    analyze_feedback_records,
    build_feedback_stats,
    build_feedback_trends,
    list_feedback_analyses,
    list_feedback_records,
)
from services.generation_guard import ACTIVE_TASK_STATUSES
from services.model_permission_service import (
    get_user_model_permissions,
    list_catalog_models,
    update_user_model_permissions,
)
from services.quota_service import get_quota_info, reset_user_quota

router = APIRouter(prefix="/api/admin", tags=["admin"])


@router.get("/catalog-models", response_model=AdminModelsListResponse)
def list_catalog_models_for_permissions(
    _: User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    """ComfyUI checkpoint + registered_models 文本模型（用于用户模型权限）。"""
    return {"models": list_catalog_models(db)}


@router.get("/stats/overview", response_model=AdminOverviewResponse)
def admin_overview_stats(
    _: User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    now = datetime.now(timezone.utc)
    today_start = now.replace(hour=0, minute=0, second=0, microsecond=0)

    total_users = db.query(User).count()
    total_tasks = db.query(Task).count()
    active_tasks = (
        db.query(Task.id)
        .filter(Task.status.in_(ACTIVE_TASK_STATUSES))
        .count()
    )
    today_users = (
        db.query(User.id)
        .filter(User.created_at >= today_start)
        .count()
    )
    today_tasks = (
        db.query(Task.id)
        .filter(Task.created_at >= today_start)
        .count()
    )
    failed_tasks = (
        db.query(Task.id)
        .filter(Task.status.in_(["failed", "timeout"]))
        .count()
    )
    failed_rate = round((failed_tasks / total_tasks) * 100, 1) if total_tasks else 0.0

    recent_rows = (
        db.query(Task, User)
        .outerjoin(User, Task.user_id == User.id)
        .order_by(Task.created_at.desc())
        .limit(5)
        .all()
    )
    recent_tasks = [
        {
            "id": task.id,
            "username": user.username if user else None,
            "task_type": task.task_type,
            "status": task.status,
            "prompt_text": (task.prompt_text or "")[:120] or None,
            "created_at": to_utc_iso(task.created_at),
        }
        for task, user in recent_rows
    ]

    return {
        "stats": {
            "total_users": total_users,
            "total_tasks": total_tasks,
            "active_tasks": active_tasks,
            "today_users": today_users,
            "today_tasks": today_tasks,
            "failed_rate": failed_rate,
        },
        "recent_tasks": recent_tasks,
    }


@router.get("/tasks", response_model=AdminTaskListResponse)
def list_all_tasks(
    page: int = 1,
    page_size: int = 20,
    status: str | None = None,
    _: User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    page = max(1, page)
    page_size = max(1, min(page_size, 100))
    query = db.query(Task, User).outerjoin(User, Task.user_id == User.id)
    if status and status.strip():
        query = query.filter(Task.status == status.strip())
    query = query.order_by(Task.created_at.desc())
    total = query.count()
    rows = query.offset((page - 1) * page_size).limit(page_size).all()
    items = []
    for task, user in rows:
        items.append(
            {
                "id": task.id,
                "user_id": task.user_id,
                "username": user.username if user else None,
                "task_type": task.task_type,
                "status": task.status,
                "progress": None,
                "prompt_text": (task.prompt_text or "")[:200] or None,
                "error": task.error,
                "created_at": to_utc_iso(task.created_at),
            }
        )
    return {
        "items": items,
        "total": total,
        "page": page,
        "page_size": page_size,
    }


@router.get("/feedback/stats", response_model=AdminFeedbackStatsResponse)
def admin_feedback_stats(
    since: str | None = None,
    until: str | None = None,
    task_type: str | None = None,
    _: User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    return build_feedback_stats(db, since=since, until=until, task_type=task_type)


@router.get("/feedback/records", response_model=AdminFeedbackRecordsResponse)
def admin_feedback_records(
    rating: int | None = None,
    model_id: str | None = None,
    task_type: str | None = None,
    since: str | None = None,
    until: str | None = None,
    limit: int = 50,
    offset: int = 0,
    admin: User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    if rating is not None and rating not in (0, 1):
        raise HTTPException(status_code=400, detail="rating 只能是 0、1 或省略")
    limit = max(1, min(limit, 200))
    offset = max(0, offset)
    return list_feedback_records(
        db,
        rating=rating,
        model_id=model_id,
        task_type=task_type,
        since=since,
        until=until,
        limit=limit,
        offset=offset,
        admin_user_id=admin.id,
    )


@router.post("/feedback/analyze", response_model=AdminFeedbackAnalyzeResponse)
async def admin_feedback_analyze(
    rating: int | None = None,
    model_id: str | None = None,
    task_type: str | None = None,
    since: str | None = None,
    until: str | None = None,
    admin: User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    if rating is not None and rating not in (0, 1):
        raise HTTPException(status_code=400, detail="rating 只能是 0、1 或省略")
    return await analyze_feedback_records(
        db,
        admin.id,
        rating=rating,
        model_id=model_id,
        task_type=task_type,
        since=since,
        until=until,
    )


@router.get("/feedback/trends", response_model=AdminFeedbackTrendsResponse)
def admin_feedback_trends(
    days: int = 30,
    _: User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    return build_feedback_trends(db, days=days)


@router.get("/feedback/analyses", response_model=AdminFeedbackAnalysesResponse)
def admin_feedback_analyses(
    limit: int = 20,
    _: User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    return list_feedback_analyses(db, limit=limit)


@router.get("/users", response_model=UserListResponse)
def list_users(
    page: int = 1,
    page_size: int = 20,
    q: str | None = None,
    _: User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    page = max(1, page)
    page_size = max(1, min(page_size, 100))
    query = db.query(User).order_by(User.id)
    if q and q.strip():
        term = f"%{q.strip()}%"
        query = query.filter(
            (User.username.ilike(term)) | (User.email.ilike(term))
        )
    total = query.count()
    users = query.offset((page - 1) * page_size).limit(page_size).all()
    items = []
    for u in users:
        items.append(
            {
                "id": u.id,
                "username": u.username,
                "email": u.email,
                "role": u.role,
                "is_active": u.is_active,
                "r2_access": bool(getattr(u, "r2_access", False)),
                "created_at": to_utc_iso(u.created_at),
                "quota": get_quota_info(db, u.id),
            }
        )
    return {"items": items, "total": total, "page": page, "page_size": page_size}


@router.get("/users/{user_id}", response_model=UserDetailResponse)
def get_user_detail(
    user_id: int,
    _: User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    user = db.get(User, user_id)
    if not user:
        raise HTTPException(status_code=404, detail="用户不存在")
    return {
        "id": user.id,
        "username": user.username,
        "email": user.email,
        "role": user.role,
        "is_active": user.is_active,
        "r2_access": bool(getattr(user, "r2_access", False)),
        "created_at": to_utc_iso(user.created_at),
        "quota": get_quota_info(db, user.id),
    }


@router.get("/users/{user_id}/models", response_model=UserModelPermissionsResponse)
def get_user_model_permissions_api(
    user_id: int,
    _: User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    return get_user_model_permissions(db, user_id)


@router.put("/users/{user_id}/models", response_model=UserModelPermissionsResponse)
def update_user_model_permissions_api(
    user_id: int,
    body: UpdateUserModelPermissionsRequest,
    _: User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    payload = [p.model_dump() for p in body.permissions]
    return update_user_model_permissions(db, user_id, payload)


@router.patch("/users/{user_id}/quota")
def update_user_quota(
    user_id: int,
    body: UpdateQuotaRequest,
    _: User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    user = db.get(User, user_id)
    if not user:
        raise HTTPException(status_code=404, detail="用户不存在")
    quota = db.query(UserQuota).filter(UserQuota.user_id == user_id).first()
    if not quota:
        raise HTTPException(status_code=404, detail="配额记录不存在")
    quota.image_limit = body.image_limit
    quota.video_limit = body.video_limit
    db.commit()
    return {"message": "配额已更新", "quota": get_quota_info(db, user_id)}


@router.patch("/users/{user_id}/role")
def update_user_role(
    user_id: int,
    body: UpdateRoleRequest,
    admin: User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    if body.role not in ("user", "admin"):
        raise HTTPException(status_code=400, detail="角色只能是 user 或 admin")
    if user_id == admin.id and body.role != "admin":
        raise HTTPException(status_code=400, detail="不能降级当前登录的管理员")
    user = db.get(User, user_id)
    if not user:
        raise HTTPException(status_code=404, detail="用户不存在")
    user.role = body.role
    db.commit()
    return {"message": "角色已更新", "role": user.role}


@router.patch("/users/{user_id}/status")
def update_user_status(
    user_id: int,
    body: UpdateStatusRequest,
    admin: User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    if user_id == admin.id and not body.is_active:
        raise HTTPException(status_code=400, detail="不能禁用当前登录的管理员")
    user = db.get(User, user_id)
    if not user:
        raise HTTPException(status_code=404, detail="用户不存在")
    user.is_active = body.is_active
    db.commit()
    return {"message": "状态已更新", "is_active": user.is_active}


@router.patch("/users/{user_id}/r2-access")
def update_user_r2_access(
    user_id: int,
    body: UpdateR2AccessRequest,
    _: User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    user = db.get(User, user_id)
    if not user:
        raise HTTPException(status_code=404, detail="用户不存在")
    user.r2_access = bool(body.r2_access)
    db.commit()
    return {"message": "R2 权限已更新", "r2_access": user.r2_access}


@router.post("/users/{user_id}/reset_quota")
def reset_quota(
    user_id: int,
    _: User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    user = db.get(User, user_id)
    if not user:
        raise HTTPException(status_code=404, detail="用户不存在")
    reset_user_quota(db, user_id)
    db.commit()
    return {"message": "配额已重置", "quota": get_quota_info(db, user_id)}
