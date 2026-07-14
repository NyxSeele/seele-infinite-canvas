from datetime import datetime

from pydantic import BaseModel, Field, field_validator


class ReviewVideoCreate(BaseModel):
    title: str = Field(..., min_length=1, max_length=200)
    description: str | None = Field(None, max_length=5000)
    video_url: str = Field(..., min_length=1, max_length=1024)
    thumbnail_url: str | None = Field(None, max_length=1024)

    @field_validator("video_url")
    @classmethod
    def video_url_must_be_http(cls, v: str) -> str:
        raw = (v or "").strip()
        if not (raw.startswith("http://") or raw.startswith("https://")):
            raise ValueError("video_url 必须是可公开访问的 http(s) 链接")
        return raw


class ReviewPresignVideoRequest(BaseModel):
    filename: str = Field(..., min_length=1, max_length=512)
    content_type: str = Field(..., min_length=1, max_length=255)
    size_bytes: int = Field(..., ge=0, le=5 * 1024 * 1024 * 1024)


class ReviewPresignVideoResponse(BaseModel):
    upload_url: str
    key: str
    content_type: str
    public_url: str
    expires_in: int = 3600


class ReviewVideoUploadResponse(BaseModel):
    key: str
    content_type: str
    public_url: str
    filename: str
    size_bytes: int


class ReviewImportVideoRequest(BaseModel):
    source_url: str = Field(..., min_length=1, max_length=2048)


class ReviewImportVideoResponse(BaseModel):
    public_url: str
    key: str | None = None
    content_type: str = "video/mp4"
    filename: str = "video.mp4"
    size_bytes: int = 0
    rehosted: bool = False


class ReviewStats(BaseModel):
    avg_rating: float | None = None
    like_count: int = 0
    dislike_count: int = 0
    comment_count: int = 0


class ReviewVideoOut(BaseModel):
    id: int
    title: str
    description: str | None = None
    video_url: str
    thumbnail_url: str | None = None
    publisher_id: int
    publisher_name: str
    published_at: datetime
    is_active: bool = True
    avg_rating: float | None = None
    like_count: int = 0
    dislike_count: int = 0
    comment_count: int = 0

    model_config = {"from_attributes": True}


class ReviewCommentCreate(BaseModel):
    reviewer_name: str = Field(..., min_length=1, max_length=64)
    rating: int = Field(..., ge=1, le=5)
    liked: bool | None = None
    comment: str | None = Field(None, max_length=2000)


class ReviewCommentOut(BaseModel):
    id: int
    video_id: int
    reviewer_name: str
    rating: int
    liked: bool | None = None
    comment: str | None = None
    created_at: datetime

    model_config = {"from_attributes": True}


class ReviewVideoDetailOut(ReviewVideoOut):
    comments: list[ReviewCommentOut] = []
