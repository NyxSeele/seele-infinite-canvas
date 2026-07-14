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


class UploadCapabilitiesResponse(BaseModel):
    r2_direct: bool
    max_size_bytes: int
