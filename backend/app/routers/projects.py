import random
from datetime import datetime

from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field
from pymongo import ReturnDocument

from app.db import db, owned
from app.errors import api_error
from app.models.alignment import Alignment
from app.models.asset import Asset
from app.models.clip import Clip
from app.models.common import utcnow
from app.models.project import Project, Stage
from app.models.script import Script
from app.services import insights, workflow
from app.services.auth import get_current_user

router = APIRouter(tags=["projects"])


class ProjectIn(BaseModel):
    title: str = Field(min_length=1)
    idea: str = ""
    target_platforms: list[str] = []


class ProjectDetail(Project):
    script: Script | None = None
    assets: list[Asset] = []
    alignment: Alignment | None = None
    clips: list[Clip] = []


@router.post("/projects", response_model=Project, status_code=201)
async def create_project(body: ProjectIn, user: dict = Depends(get_current_user)):
    now = utcnow()
    doc = {
        "user_id": user["_id"], **body.model_dump(),
        "stage": "idea", "stage_history": [{"stage": "idea", "at": now}],
        "script_id": None, "footage_asset_ids": [], "scheduled_for": None, "published_at": None, "tags": [],
        "created_at": now, "updated_at": now,
    }
    doc["_id"] = (await db.projects.insert_one(doc)).inserted_id
    return doc


@router.get("/projects", response_model=list[Project])
async def list_projects(stage: Stage | None = None, user: dict = Depends(get_current_user)):
    q: dict = {"user_id": user["_id"]}
    if stage:
        q["stage"] = stage
    return await db.projects.find(q).sort("updated_at", -1).to_list(500)


@router.get("/projects/{project_id}", response_model=ProjectDetail)
async def get_project(project_id: str, user: dict = Depends(get_current_user)):
    p = await owned("projects", project_id, user)
    return {
        **p,
        "script": await db.scripts.find_one({"_id": p["script_id"]}) if p.get("script_id") else None,
        "assets": await db.assets.find({"_id": {"$in": p["footage_asset_ids"]}}).to_list(100),
        "alignment": await db.alignments.find_one({"project_id": p["_id"]}),
        "clips": await db.clips.find({"project_id": p["_id"]}).sort("scores.overall", -1).to_list(100),
    }


class ProjectPatch(BaseModel):
    title: str | None = Field(None, min_length=1)
    idea: str | None = None
    target_platforms: list[str] | None = None
    scheduled_for: datetime | None = None
    tags: list[str] | None = None


class StageIn(BaseModel):
    stage: Stage


@router.patch("/projects/{project_id}", response_model=Project)
async def update_project(project_id: str, body: ProjectPatch, user: dict = Depends(get_current_user)):
    p = await owned("projects", project_id, user)
    fields = body.model_dump(exclude_unset=True)
    return await db.projects.find_one_and_update(
        {"_id": p["_id"]}, {"$set": {**fields, "updated_at": utcnow()}}, return_document=ReturnDocument.AFTER)


@router.patch("/projects/{project_id}/stage", response_model=Project)
async def move_stage(project_id: str, body: StageIn, user: dict = Depends(get_current_user)):
    """F7 kanban move (any direction). Appends stage_history."""
    p = await owned("projects", project_id, user)
    if p["stage"] == body.stage:
        return p
    return await workflow.set_stage(p["_id"], body.stage)


@router.post("/projects/{project_id}/publish", response_model=Project)
async def publish(project_id: str, user: dict = Depends(get_current_user)):
    """MOCK publish: marks the project published and records mock analytics for each ready clip x platform
    (no real platform APIs are connected)."""
    p = await owned("projects", project_id, user)
    clips = await db.clips.find({"project_id": p["_id"], "kind": "short", "status": {"$in": ["approved", "exported"]}}).to_list(50)
    if not clips:
        raise api_error(400, "Approve or export at least one clip before publishing", "NOTHING_TO_PUBLISH")
    rng, now, docs = random.Random(), utcnow(), []
    for c in clips:
        hook = await db.generated_content.find_one({"clip_id": c["_id"], "type": "hook", "variants.selected": True}, sort=[("created_at", -1)])
        hook_type = next((v["label"] for v in hook["variants"] if v["selected"]), None) if hook else None
        hook_type = hook_type if hook_type in insights.MOCK_HOOKS else rng.choice(list(insights.MOCK_HOOKS))
        for platform in [v["platform"] for v in c.get("variants", [])] or p["target_platforms"] or ["shorts"]:
            if platform in insights.MOCK_PLATFORMS:
                docs.append({"user_id": user["_id"], "project_id": p["_id"], "clip_id": c["_id"],
                             **insights.mock_post(rng, platform, hook_type, now, c["title"])})
    if docs:
        await db.analytics.insert_many(docs)
    return await workflow.set_stage(p["_id"], "published")
