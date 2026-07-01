"""向后兼容：请优先使用 services.quota_service。"""
from models.quota import first_day_of_month
from services.quota_service import (
    QuotaExceededError,
    check_and_consume,
    create_task_record,
    get_quota_info,
    get_or_create_user_quota,
)

check_and_consume_quota = check_and_consume


def quota_status_dict(user_id_or_quota, db=None):
    """兼容旧调用：quota_status_dict(quota) 或 get_quota_info(db, user_id)。"""
    if db is not None:
        return get_quota_info(db, user_id_or_quota)
    from services.quota_service import days_until_reset

    quota = user_id_or_quota

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

__all__ = [
    "QuotaExceededError",
    "first_day_of_month",
    "get_or_create_user_quota",
    "get_quota_info",
    "quota_status_dict",
    "check_and_consume",
    "check_and_consume_quota",
    "create_task_record",
]
