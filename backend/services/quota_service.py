from datetime import date

from sqlalchemy import update
from sqlalchemy.orm import Session

from models import QuotaPlan, Task, UserQuota
from models.quota import first_day_of_month


class QuotaExceededError(Exception):
    def __init__(self, message: str):
        self.message = message
        super().__init__(message)


def next_month_first(d: date | None = None) -> date:
    d = d or date.today()
    if d.month == 12:
        return date(d.year + 1, 1, 1)
    return date(d.year, d.month + 1, 1)


def days_until_reset(today: date | None = None) -> int:
    today = today or date.today()
    return (next_month_first(today) - today).days


def format_reset_date() -> str:
    nxt = next_month_first()
    return f"{nxt.month}月{nxt.day}日"


def _maybe_reset_period(quota: UserQuota, db: Session) -> None:
    current_period = first_day_of_month()
    if quota.period_start != current_period:
        quota.image_used = 0
        quota.video_used = 0
        quota.period_start = current_period
        db.flush()


def get_or_create_user_quota(db: Session, user_id: int) -> UserQuota:
    quota = db.query(UserQuota).filter(UserQuota.user_id == user_id).first()
    if quota:
        _maybe_reset_period(quota, db)
        return quota

    plan = db.query(QuotaPlan).filter(QuotaPlan.name == "default").first()
    if not plan:
        raise RuntimeError("缺少 default 配额计划，请重新初始化数据库")

    quota = UserQuota(
        user_id=user_id,
        plan_name=plan.name,
        image_limit=plan.image_limit,
        video_limit=plan.video_limit,
        image_used=0,
        video_used=0,
        period_start=first_day_of_month(),
    )
    db.add(quota)
    db.flush()
    return quota


def get_quota_info(db: Session, user_id: int) -> dict:
    quota = get_or_create_user_quota(db, user_id)
    _maybe_reset_period(quota, db)

    def remaining(limit: int, used: int) -> int | None:
        if limit < 0:
            return None
        return max(0, limit - used)

    return {
        "image_limit": quota.image_limit,
        "image_used": quota.image_used,
        "image_remaining": remaining(quota.image_limit, quota.image_used),
        "video_limit": quota.video_limit,
        "video_used": quota.video_used,
        "video_remaining": remaining(quota.video_limit, quota.video_used),
        "period_start": quota.period_start.isoformat(),
        "days_until_reset": days_until_reset(),
    }


def check_and_consume(db: Session, user_id: int, task_type: str) -> UserQuota:
    """检查并扣减配额；-1 表示无限。"""
    if task_type not in ("image", "video"):
        raise ValueError("task_type 必须为 image 或 video")

    quota = get_or_create_user_quota(db, user_id)
    _maybe_reset_period(quota, db)

    if task_type == "image":
        limit, used_val = quota.image_limit, quota.image_used
        label = "图像生成"
        stmt = (
            update(UserQuota)
            .where(UserQuota.id == quota.id)
            .where(UserQuota.image_limit >= 0)
            .where(UserQuota.image_used < UserQuota.image_limit)
            .values(image_used=UserQuota.image_used + 1)
        )
    else:
        limit, used_val = quota.video_limit, quota.video_used
        label = "视频生成"
        stmt = (
            update(UserQuota)
            .where(UserQuota.id == quota.id)
            .where(UserQuota.video_limit >= 0)
            .where(UserQuota.video_used < UserQuota.video_limit)
            .values(video_used=UserQuota.video_used + 1)
        )

    if limit < 0:
        return quota

    if used_val >= limit:
        raise QuotaExceededError(
            f"本月{label}配额已用完（{used_val}/{limit}），下次重置：{format_reset_date()}"
        )

    result = db.execute(stmt)
    if result.rowcount == 0:
        db.refresh(quota)
        used_now = quota.image_used if task_type == "image" else quota.video_used
        lim = quota.image_limit if task_type == "image" else quota.video_limit
        raise QuotaExceededError(
            f"本月{label}配额已用完（{used_now}/{lim}），下次重置：{format_reset_date()}"
        )

    db.refresh(quota)
    return quota


def create_task_record(
    db: Session,
    task_id: str,
    task_type: str,
    status: str = "pending",
    user_id: int | None = None,
    team_id: str | None = None,
    prompt_text: str | None = None,
    comfyui_prompt_id: str | None = None,
    node_id: str | None = None,
    sound_note: str | None = None,
    video_backend: str | None = None,
    use_reactor: bool = False,
    reactor_face_image: str | None = None,
) -> Task:
    existing = db.get(Task, task_id)
    if existing:
        if prompt_text and not existing.prompt_text:
            existing.prompt_text = prompt_text
        if user_id is not None and existing.user_id is None:
            existing.user_id = user_id
        if sound_note and not existing.sound_note:
            existing.sound_note = sound_note
        if video_backend and not existing.video_backend:
            existing.video_backend = video_backend
        if use_reactor and not existing.use_reactor:
            existing.use_reactor = True
        if reactor_face_image and not existing.reactor_face_image:
            existing.reactor_face_image = reactor_face_image
        db.flush()
        return existing
    task = Task(
        id=task_id,
        user_id=user_id,
        team_id=team_id,
        task_type=task_type,
        status=status,
        prompt_text=prompt_text,
        comfyui_prompt_id=comfyui_prompt_id,
        node_id=node_id,
        sound_note=sound_note,
        video_backend=video_backend,
        use_reactor=bool(use_reactor),
        reactor_face_image=(reactor_face_image or "").strip() or None,
    )
    db.add(task)
    db.flush()
    return task


def reset_user_quota(db: Session, user_id: int) -> UserQuota:
    quota = get_or_create_user_quota(db, user_id)
    quota.image_used = 0
    quota.video_used = 0
    quota.period_start = first_day_of_month()
    db.flush()
    return quota
