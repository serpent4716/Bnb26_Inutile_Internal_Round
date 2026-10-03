from datetime import datetime
from typing import Literal

from pydantic import BaseModel

from app.models.common import MongoModel, PyObjectId

Platform = Literal["youtube", "shorts", "reels", "tiktok", "linkedin", "x"]


class Variant(BaseModel):
    text: str
    selected: bool = False
    score: float | None = None
    label: str | None = None  # hook type ("question", "bold_claim", ...) or an idea's title


class GeneratedContent(MongoModel):
    user_id: PyObjectId | None = None
    project_id: PyObjectId | None = None
    clip_id: PyObjectId | None = None
    type: Literal["hook", "title", "caption", "hashtags", "description", "thumbnail_text", "script", "ideas", "insights"]
    platform: Platform | None = None
    variants: list[Variant] = []
    prompt_context: str = ""
    created_at: datetime | None = None
