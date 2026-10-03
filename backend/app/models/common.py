from datetime import datetime, timezone
from typing import Annotated

from bson import ObjectId
from pydantic import BaseModel, BeforeValidator, ConfigDict, Field

# Shared ObjectId -> str helper: any field typed PyObjectId serializes as a string.
PyObjectId = Annotated[str, BeforeValidator(lambda v: str(v) if isinstance(v, ObjectId) else v)]


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


class MongoModel(BaseModel):
    """Reads `_id` from Mongo docs, outputs it as `id`."""

    model_config = ConfigDict(populate_by_name=True)
    id: PyObjectId | None = Field(default=None, validation_alias="_id")
