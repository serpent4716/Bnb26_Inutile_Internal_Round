from fastapi import APIRouter, Depends
from pydantic import BaseModel

from app.db import db, owned
from app.errors import api_error
from app.models.common import utcnow
from app.models.script import Script
from app.services.auth import get_current_user
from app.services.scripts import label_sections, parse_lines
from app.services.workflow import advance

router = APIRouter(tags=["scripts"])


class ScriptIn(BaseModel):
    project_id: str
    content: str


@router.post("/scripts", response_model=Script, status_code=201)
async def create_script(body: ScriptIn, user: dict = Depends(get_current_user)):
    project = await owned("projects", body.project_id, user)
    lines = parse_lines(body.content)
    if not lines:
        raise api_error(400, "Script is empty", "EMPTY_SCRIPT")
    sections = await label_sections(lines)

    previous = await db.scripts.find_one({"_id": project.get("script_id")}, {"version": 1}) if project.get("script_id") else None
    doc = {
        "user_id": user["_id"],
        "project_id": project["_id"],
        "title": project["title"],
        "content": body.content,
        "lines": [{"idx": i, "text": t, "section": s} for i, (t, s) in enumerate(zip(lines, sections))],
        "source": "user",
        "version": previous["version"] + 1 if previous else 1,
        "created_at": utcnow(),
    }
    doc["_id"] = (await db.scripts.insert_one(doc)).inserted_id
    await db.projects.update_one({"_id": project["_id"]}, {"$set": {"script_id": doc["_id"], "updated_at": utcnow()}})
    await advance(project["_id"], "recording")  # F7: scripting done
    return doc
