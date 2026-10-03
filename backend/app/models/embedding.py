from typing import Literal

from app.models.common import MongoModel, PyObjectId


class Embedding(MongoModel):
    user_id: PyObjectId
    asset_id: PyObjectId | None = None
    kind: Literal["transcript_chunk", "visual_description", "script"]
    text: str
    start: float | None = None
    end: float | None = None
    vector: list[float] = []
