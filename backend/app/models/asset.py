from datetime import datetime
from typing import Literal

from pydantic import BaseModel

from app.models.common import MongoModel, PyObjectId


class AssetMetadata(BaseModel):
    duration: float | None = None
    width: int | None = None
    height: int | None = None
    fps: float | None = None


class Keyframe(BaseModel):
    t: float
    description: str


class AssetAI(BaseModel):
    tags: list[str] = []
    description: str = ""
    keyframes: list[Keyframe] = []
    transcript_id: PyObjectId | None = None
    status: Literal["pending", "processing", "ready", "failed"] = "pending"


class Asset(MongoModel):
    user_id: PyObjectId
    project_id: PyObjectId | None = None
    type: Literal["video", "image", "audio", "document"]
    filename: str
    storage_url: str
    thumbnail_url: str | None = None
    mime_type: str | None = None
    size_bytes: int | None = None
    metadata: AssetMetadata = AssetMetadata()
    ai: AssetAI = AssetAI()
    created_at: datetime | None = None
