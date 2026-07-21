from pydantic import BaseModel, Field


class CanvasImagePresignRequest(BaseModel):
    filename: str = Field(..., min_length=1, max_length=512)
    content_type: str = Field(..., min_length=1, max_length=255)
    size_bytes: int = Field(..., ge=0)


class CanvasImagePresignResponse(BaseModel):
    upload_url: str
    key: str
    content_type: str
    expires_in: int = 3600


class CanvasImageRegisterRequest(BaseModel):
    key: str = Field(..., min_length=1, max_length=1024)
    content_type: str = Field(..., min_length=1, max_length=255)
    filename: str | None = Field(None, max_length=512)
    width: int | None = Field(None, ge=1, le=8192)
    height: int | None = Field(None, ge=1, le=8192)


class CanvasImageRegisterResponse(BaseModel):
    url: str
    key: str
    width: int
    height: int
    aspect_ratio: str


class StorageFeatureCapabilities(BaseModel):
    backend: str
    max_size_bytes: int | None = None
    r2_public_url: str | None = None


class UploadCapabilitiesResponse(BaseModel):
    r2_direct: bool
    max_size_bytes: int
    r2_public_url: str | None = None
    media_public_base: str | None = None
    canvas: StorageFeatureCapabilities | None = None
    team: StorageFeatureCapabilities | None = None
    review: StorageFeatureCapabilities | None = None
