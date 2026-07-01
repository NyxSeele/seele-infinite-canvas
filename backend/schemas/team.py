from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field

TeamRole = Literal["owner", "admin", "editor", "viewer"]


class TeamCreate(BaseModel):
    name: str = Field(..., min_length=1, max_length=128)


class TeamUpdate(BaseModel):
    name: str | None = Field(None, min_length=1, max_length=128)


class TeamMemberAdd(BaseModel):
    username: str = Field(..., min_length=1, max_length=64)
    role: TeamRole = "editor"


class TeamMemberUpdate(BaseModel):
    role: TeamRole


class MemberQuotaUsage(BaseModel):
    image_limit: int = 50
    image_used: int = 0
    video_limit: int = 10
    video_used: int = 0


class TeamMemberOut(BaseModel):
    user_id: int
    username: str
    email: str | None = None
    role: str
    joined_at: datetime
    quota_settings: dict = {}
    quota: MemberQuotaUsage | None = None


class TeamOut(BaseModel):
    id: str
    name: str
    owner_id: int
    owner_username: str | None = None
    my_role: str
    created_at: datetime
    member_count: int = 0


class TeamListResponse(BaseModel):
    owned: TeamOut | None = None
    joined: list[TeamOut] = []


class TeamInviteSettings(BaseModel):
    expiryDays: int = 7
    maxUses: int = 0
    quotaType: str = "unlimited"
    periodicCycle: str = "monthly"
    periodicAmount: int = 20000
    fixedAmount: int = 20000


class TeamInviteCreate(BaseModel):
    settings: TeamInviteSettings | None = None


class TeamInviteOut(BaseModel):
    token: str
    team_id: str
    url: str
    expires_at: datetime | None = None
    max_uses: int = 0
    use_count: int = 0
    settings: dict = {}
    created_at: datetime


class TeamInvitePreview(BaseModel):
    team: TeamOut
    settings: dict = {}
    already_member: bool = False
    my_role: str | None = None


class TeamJoinRequest(BaseModel):
    token: str = Field(..., min_length=8, max_length=64)
