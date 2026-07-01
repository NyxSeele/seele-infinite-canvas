from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field

AssetKind = Literal["character", "scene", "prop", "other"]


class AssetCreate(BaseModel):
    name: str = Field(..., min_length=1, max_length=128)
    kind: AssetKind = "other"
    image_url: str = Field(..., min_length=1, max_length=1024)
    note: str | None = Field(None, max_length=2000)
    source_canvas_id: str | None = Field(None, max_length=64)
    source_canvas_name: str | None = Field(None, max_length=256)
    source_node_id: str | None = Field(None, max_length=64)
    team_id: str | None = Field(None, max_length=36)


class AssetUpdate(BaseModel):
    name: str | None = Field(None, min_length=1, max_length=128)
    kind: AssetKind | None = None
    image_url: str | None = Field(None, min_length=1, max_length=1024)
    note: str | None = Field(None, max_length=2000)
    source_canvas_id: str | None = Field(None, max_length=64)
    source_canvas_name: str | None = Field(None, max_length=256)
    source_node_id: str | None = Field(None, max_length=64)
    team_id: str | None = Field(None, max_length=36)


class AssetOut(BaseModel):
    id: str
    name: str
    kind: str
    image_url: str
    note: str | None = None
    source_canvas_id: str | None = None
    source_canvas_name: str | None = None
    source_node_id: str | None = None
    team_id: str | None = None
    team_name: str | None = None
    owner_id: int | None = None
    owner_name: str | None = None
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}
