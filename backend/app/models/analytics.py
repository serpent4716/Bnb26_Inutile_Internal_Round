from datetime import datetime

from pydantic import BaseModel

from app.models.common import MongoModel, PyObjectId


class Metrics(BaseModel):
    views: int = 0
    likes: int = 0
    comments: int = 0
    shares: int = 0
    watch_time_avg: float = 0
    retention_3s: float = 0


class Analytics(MongoModel):
    user_id: PyObjectId
    project_id: PyObjectId | None = None
    clip_id: PyObjectId | None = None
    platform: str
    posted_at: datetime | None = None
    metrics: Metrics = Metrics()
    hook_type: str | None = None  # "question" | "bold_claim" | "story" ...
    title: str = ""
    snapshot_at: datetime | None = None
    mock: bool = False  # MOCK: seeded or mock-published, not from a real platform
