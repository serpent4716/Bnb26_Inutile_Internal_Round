from datetime import datetime
from typing import Literal

from pydantic import BaseModel

from app.models.common import MongoModel, PyObjectId


class ScriptLine(BaseModel):
    idx: int
    text: str
    section: Literal["hook", "intro", "body", "cta"] = "body"


class Script(MongoModel):
    user_id: PyObjectId
    project_id: PyObjectId | None = None
    title: str = ""
    content: str
    lines: list[ScriptLine] = []
    source: Literal["user", "ai_generated"] = "user"
    version: int = 1
    created_at: datetime | None = None
