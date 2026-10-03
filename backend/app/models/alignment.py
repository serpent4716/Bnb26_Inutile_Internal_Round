from datetime import datetime
from typing import Literal

from pydantic import BaseModel

from app.models.common import MongoModel, PyObjectId


class Take(BaseModel):
    start: float
    end: float
    similarity: float
    transcript_segment_idxs: list[int] = []
    visual: str | None = None  # description of the nearest described keyframe


class LineMatch(BaseModel):
    script_line_idx: int
    takes: list[Take] = []
    best_take_index: int | None = None
    status: Literal["matched", "missing", "ad_libbed"]


class TextRange(BaseModel):
    start: float
    end: float
    text: str


class Alignment(MongoModel):
    project_id: PyObjectId
    script_id: PyObjectId
    asset_id: PyObjectId
    matches: list[LineMatch] = []
    unscripted_ranges: list[TextRange] = []
    coverage: float = 0.0
    created_at: datetime | None = None
