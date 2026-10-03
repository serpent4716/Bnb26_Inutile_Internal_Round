from datetime import datetime

from pydantic import BaseModel

from app.models.common import MongoModel, PyObjectId


class Word(BaseModel):
    w: str
    start: float
    end: float
    conf: float | None = None


class Segment(BaseModel):
    idx: int
    start: float
    end: float
    text: str
    words: list[Word] = []
    is_filler: bool = False
    silence_after: float = 0.0


class Transcript(MongoModel):
    asset_id: PyObjectId
    language: str | None = None
    full_text: str = ""
    segments: list[Segment] = []
    created_at: datetime | None = None
