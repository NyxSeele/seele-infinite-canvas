from pydantic import BaseModel

from schemas.auth import UserInfo


class QuotaInfo(BaseModel):
    image_limit: int
    image_used: int
    image_remaining: int | None = None
    video_limit: int
    video_used: int
    video_remaining: int | None = None
    period_start: str
    days_until_reset: int


class MeResponse(BaseModel):
    id: int
    username: str
    email: str
    role: str
    quota: QuotaInfo
