from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field, model_validator


class PresignUploadRequest(BaseModel):
    filename: str = Field(..., min_length=1, max_length=512)
    content_type: str = Field(..., min_length=1, max_length=255)
    size_bytes: int = Field(..., ge=0)
    description: str | None = Field(None, max_length=2000)


class PresignUploadResponse(BaseModel):
    upload_url: str
    key: str
    content_type: str
    expires_in: int = 3600


class FileRegisterRequest(BaseModel):
    key: str = Field(..., min_length=1, max_length=1024)
    filename: str = Field(..., min_length=1, max_length=512)
    content_type: str = Field(..., min_length=1, max_length=255)
    size_bytes: int = Field(..., ge=0)
    description: str | None = Field(None, max_length=2000)


class R2FileOut(BaseModel):
    id: int
    key: str
    filename: str
    content_type: str
    size_bytes: int
    uploader_id: int
    uploader_name: str
    uploaded_at: datetime
    description: str | None = None
    category: str = "other"
    public_url: str | None = None
    storage_backend: str = "r2"
    local_rel_path: str | None = None

    model_config = {"from_attributes": True}


class R2FileListResponse(BaseModel):
    items: list[R2FileOut]
    total: int


class DownloadUrlResponse(BaseModel):
    download_url: str
    expires_in: int = 3600


class AddToAssetsRequest(BaseModel):
    target: Literal["personal", "team"]
    team_id: str | None = Field(None, max_length=36)

    @model_validator(mode="after")
    def team_id_required_for_team(self) -> "AddToAssetsRequest":
        if self.target == "team" and not (self.team_id or "").strip():
            raise ValueError("target=team 时必须提供 team_id")
        return self


class UpdateR2AccessRequest(BaseModel):
    r2_access: bool


class ImportVideoRequest(BaseModel):
    source_url: str = Field(..., min_length=1, max_length=2048)
    description: str | None = Field(None, max_length=2000)
    team_id: str | None = Field(None, max_length=36)


class ImportVideoResponse(BaseModel):
    file: R2FileOut
    rehosted: bool = False
    skipped: bool = False
