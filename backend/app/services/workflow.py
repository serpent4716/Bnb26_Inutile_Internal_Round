"""F7: project stages. Every change appends stage_history (it powers production insights)."""

from bson import ObjectId

from app.db import db
from app.models.common import utcnow

STAGES = ["idea", "scripting", "recording", "editing", "review", "scheduled", "published"]


async def set_stage(project_id: ObjectId, stage: str) -> dict:
    now = utcnow()
    update = {"$set": {"stage": stage, "updated_at": now}, "$push": {"stage_history": {"stage": stage, "at": now}}}
    if stage == "published":
        update["$set"]["published_at"] = now
    return await db.projects.find_one_and_update({"_id": project_id}, update, return_document=True)


async def advance(project_id: ObjectId | None, stage: str) -> None:
    """Auto-advance: move forward to `stage`, never backwards (a creator's manual move wins)."""
    if not project_id:
        return
    project = await db.projects.find_one({"_id": project_id}, {"stage": 1})
    if project and STAGES.index(stage) > STAGES.index(project["stage"]):
        await set_stage(project_id, stage)
