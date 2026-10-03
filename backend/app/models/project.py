from datetime import datetime
from typing import Literal

from pydantic import BaseModel

from app.models.common import MongoModel, PyObjectId

Stage = Literal["idea", "scripting", "recording", "editing", "review", "scheduled", "published"]


class StageEvent(BaseModel):
    stage: Stage
    at: datetime


class Project(MongoModel):
    user_id: PyObjectId
    title: str
    idea: str = ""
    stage: Stage = "idea"
    stage_history: list[StageEvent] = []
    script_id: PyObjectId | None = None
    footage_asset_ids: list[PyObjectId] = []
    target_platforms: list[str] = []
    scheduled_for: datetime | None = None
    published_at: datetime | None = None
    tags: list[str] = []
    created_at: datetime | None = None
    updated_at: datetime | None = None
