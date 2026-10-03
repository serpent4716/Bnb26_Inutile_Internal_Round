from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field, model_validator

from app.models.common import MongoModel, PyObjectId


class Scores(BaseModel):
    hook: float = 0
    completeness: float = 0
    virality: float = 0
    overall: float = 0


class EDLSegment(BaseModel):
    start: float = Field(ge=0)
    end: float

    @model_validator(mode="after")
    def _ordered(self):
        if self.end <= self.start:
            raise ValueError("segment end must be after start")
        return self


class Caption(BaseModel):
    start: float
    end: float
    text: str
    style: str = "bold"


class Zoom(BaseModel):
    start: float
    end: float
    scale: float


class CropPoint(BaseModel):
    t: float
    x_center: float


class Overlay(BaseModel):
    type: str                      # "hook" (text) | "image" | "broll" ...
    asset_id: PyObjectId | None = None
    text: str | None = None        # for text overlays like the selected hook
    start: float
    end: float


class EDL(BaseModel):
    aspect_ratio: Literal["16:9", "9:16", "1:1"] = "16:9"
    caption_style: Literal["bold_center", "clean_bottom"] = "bold_center"
    segments: list[EDLSegment] = []
    captions: list[Caption] = []
    zooms: list[Zoom] = []
    crop_track: list[CropPoint] = []
    overlays: list[Overlay] = []


class EDLVersion(BaseModel):
    edl: EDL
    edited_by: Literal["ai", "user"]
    at: datetime


class Render(BaseModel):
    status: str | None = None
    url: str | None = None
    rendered_at: datetime | None = None


class PlatformVariant(BaseModel):
    """F6: a per-platform version of the clip (own aspect, length, captions, render)."""
    platform: str
    edl: EDL
    render: Render = Render()


class Clip(MongoModel):
    project_id: PyObjectId
    source_asset_id: PyObjectId
    kind: Literal["short", "rough_cut"] = "short"
    title: str = ""
    reason: str = ""
    scores: Scores = Scores()
    edl: EDL = EDL()
    edl_versions: list[EDLVersion] = []
    render: Render = Render()
    variants: list[PlatformVariant] = []
    status: Literal["suggested", "approved", "rejected", "exported"] = "suggested"
    created_at: datetime | None = None
