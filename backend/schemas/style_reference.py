from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field


class StyleReferenceData(BaseModel):
    color_tone: str = ""
    lighting: str = ""
    shot_language: str = ""
    atmosphere: str = ""
    style_keywords: list[str] = Field(default_factory=list)
    source: Literal["user_upload"] = "user_upload"
    extracted_at: str = ""
    display_summary: str = ""
    source_video_url: str = ""


class StyleReferenceUpdateRequest(BaseModel):
    color_tone: str | None = None
    lighting: str | None = None
    shot_language: str | None = None
    atmosphere: str | None = None
    style_keywords: list[str] | None = None
    display_summary: str | None = None
