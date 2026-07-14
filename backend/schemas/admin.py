from pydantic import BaseModel, Field

from schemas.quota import QuotaInfo


class UserListItem(BaseModel):
    id: int
    username: str
    email: str
    role: str
    is_active: bool
    r2_access: bool = False
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


class UpdateR2AccessRequest(BaseModel):
    r2_access: bool


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
    r2_access: bool = False
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


class AdminFeedbackModelStats(BaseModel):
    model_id: str
    total: int
    satisfied: int
    rate: float


class AdminFeedbackStatsResponse(BaseModel):
    total: int
    satisfied: int
    unsatisfied: int
    by_model: list[AdminFeedbackModelStats]
    tag_counts: dict[str, int]
    tag_counts_by_model: dict[str, dict[str, int]] = {}
    tag_cooccurrence: list[dict] = []


class AdminFeedbackRecordItem(BaseModel):
    task_id: str
    task_type: str
    model_id: str
    original_input: str | None = None
    compiled_prompt: str | None = None
    user_rating: int
    rating_tags: list[str] = []
    rating_comment: str | None = None
    generation_params: dict = {}
    result: str | None = None
    result_url: str | None = None
    rated_at: str | None = None
    completed_at: str | None = None
    generation_seconds: float | None = None


class AdminFeedbackRecordsResponse(BaseModel):
    items: list[AdminFeedbackRecordItem]
    total: int
    limit: int
    offset: int


class AdminFeedbackAnalyzeResponse(BaseModel):
    analysis: str
    analysis_json: dict | None = None
    vision_count: int = 0
    vision_meta: list[dict] = []
    llm_model_id: str | None = None
    run_id: str | None = None


class AdminFeedbackTrendPoint(BaseModel):
    date: str
    total: int
    satisfied_rate: float
    top_tag: str | None = None


class AdminFeedbackTrendsResponse(BaseModel):
    days: int
    series: list[AdminFeedbackTrendPoint]


class AdminFeedbackAnalysisItem(BaseModel):
    id: str
    created_at: str | None = None
    record_count: int
    vision_count: int
    analysis: str
    analysis_json: dict | None = None


class AdminFeedbackAnalysesResponse(BaseModel):
    items: list[AdminFeedbackAnalysisItem]


class AdminFileItem(BaseModel):
    id: str
    source: str
    source_id: str
    user_id: int | None = None
    username: str | None = None
    filename: str
    category: str
    content_type: str | None = None
    size_bytes: int | None = None
    url: str | None = None
    preview_url: str | None = None
    download_url: str | None = None
    thumbnail_url: str | None = None
    created_at: str | None = None
    description: str | None = None
    meta: dict = {}


class AdminFileListResponse(BaseModel):
    items: list[AdminFileItem]
    total: int
    page: int
    page_size: int


class AdminFileStatsResponse(BaseModel):
    total: int
    by_source: dict[str, int]
    storage_bytes: dict[str, int] = {}
