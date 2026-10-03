from datetime import datetime
from typing import Literal

from app.models.common import MongoModel, PyObjectId


class Job(MongoModel):
    user_id: PyObjectId
    project_id: PyObjectId | None = None
    type: Literal["pipeline", "transcription", "render", "tagging", "adapt"]
    status: Literal["queued", "running", "done", "failed"] = "queued"
    current_step: str = ""
    progress: int = 0
    error: str | None = None
    created_at: datetime | None = None
    finished_at: datetime | None = None
