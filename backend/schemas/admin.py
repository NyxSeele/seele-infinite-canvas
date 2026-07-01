from pydantic import BaseModel, Field

from schemas.quota import QuotaInfo


class UserListItem(BaseModel):
    id: int
    username: str
    email: str
    role: str
    is_active: bool
    created_at: str | None = None
    quota: QuotaInfo


class UserListResponse(BaseModel):
    items: list[UserListItem]
    total: int
    page: int
    page_size: int = 20


class UpdateQuotaRequest(BaseModel):
    image_limit: int = Field(..., description="-1 表示无限")
    video_limit: int = Field(..., description="-1 表示无限")


class UpdateStatusRequest(BaseModel):
    is_active: bool


class UpdateRoleRequest(BaseModel):
    role: str = Field(..., description="user 或 admin")


class ModelPermissionItem(BaseModel):
    model_id: str
    enabled: bool


class UserModelPermissionsResponse(BaseModel):
    user_id: int
    permissions: list[ModelPermissionItem]


class UpdateUserModelPermissionsRequest(BaseModel):
    permissions: list[ModelPermissionItem]


class AdminModelItem(BaseModel):
    model_id: str
    name: str
    type: str


class AdminModelsListResponse(BaseModel):
    models: list[AdminModelItem]


class UserDetailResponse(BaseModel):
    id: int
    username: str
    email: str
    role: str
    is_active: bool
    created_at: str | None = None
    quota: QuotaInfo


class AdminTaskItem(BaseModel):
    id: str
    user_id: int | None = None
    username: str | None = None
    task_type: str
    status: str
    progress: int | None = None
    prompt_text: str | None = None
    error: str | None = None
    created_at: str | None = None


class AdminTaskListResponse(BaseModel):
    items: list[AdminTaskItem]
    total: int
    page: int
    page_size: int


class AdminOverviewStats(BaseModel):
    total_users: int
    total_tasks: int
    active_tasks: int
    today_users: int = 0
    today_tasks: int = 0
    failed_rate: float = 0.0


class AdminRecentTaskItem(BaseModel):
    id: str
    username: str | None = None
    task_type: str
    status: str
    prompt_text: str | None = None
    created_at: str | None = None


class AdminOverviewResponse(BaseModel):
    stats: AdminOverviewStats
    recent_tasks: list[AdminRecentTaskItem] = []
