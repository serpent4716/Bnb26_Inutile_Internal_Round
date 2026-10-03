from fastapi import APIRouter, BackgroundTasks, Depends
from pydantic import BaseModel

from app.db import db, oid, owned
from app.errors import api_error
from app.jobs.runner import create_job, run_job
from app.models.alignment import Alignment
from app.models.clip import Clip
from app.models.common import utcnow
from app.models.job import Job
from app.services.alignment import rough_cut_edl
from app.services.auth import get_current_user
from app.services.pipeline import run_pipeline

router = APIRouter(tags=["processing"])


class BestTakeIn(BaseModel):
    best_take_index: int


@router.post("/projects/{project_id}/process", status_code=202)
async def process_project(project_id: str, bg: BackgroundTasks, user: dict = Depends(get_current_user)):
    project = await owned("projects", project_id, user)
    if not project.get("script_id"):
        raise api_error(400, "Add a script first", "NO_SCRIPT")
    if not project["footage_asset_ids"]:
        raise api_error(400, "Upload footage first", "NO_FOOTAGE")
    asset = await db.assets.find_one({"_id": project["footage_asset_ids"][-1]}, {"ai.status": 1})
    if asset["ai"]["status"] in ("pending", "processing"):
        raise api_error(409, "Footage is still being transcribed", "FOOTAGE_BUSY")
    job_id = await create_job("pipeline", user["_id"], project["_id"])
    run_job(bg, job_id, run_pipeline, str(project["_id"]))
    return {"job_id": job_id}


@router.get("/jobs", response_model=list[Job])
async def list_jobs(active: bool = False, user: dict = Depends(get_current_user)):
    """Recent jobs; active=true -> only queued/running (dashboard)."""
    q: dict = {"user_id": user["_id"]}
    if active:
        q["status"] = {"$in": ["queued", "running"]}
    return await db.jobs.find(q).sort("created_at", -1).to_list(20)


@router.get("/jobs/{job_id}", response_model=Job)
async def get_job(job_id: str, user: dict = Depends(get_current_user)):
    return await owned("jobs", job_id, user)


@router.get("/projects/{project_id}/alignment", response_model=Alignment)
async def get_alignment(project_id: str, user: dict = Depends(get_current_user)):
    project = await owned("projects", project_id, user)
    alignment = await db.alignments.find_one({"project_id": project["_id"]})
    if not alignment:
        raise api_error(404, "Project hasn't been processed yet", "ALIGNMENT_NOT_READY")
    return alignment


@router.patch("/alignments/{alignment_id}/lines/{idx}", response_model=Alignment)
async def set_best_take(alignment_id: str, idx: int, body: BestTakeIn, user: dict = Depends(get_current_user)):
    alignment = await db.alignments.find_one({"_id": oid(alignment_id)})
    if not alignment or not await db.projects.find_one({"_id": alignment["project_id"], "user_id": user["_id"]}, {"_id": 1}):
        raise api_error(404, "Alignment not found", "NOT_FOUND")
    match = next((m for m in alignment["matches"] if m["script_line_idx"] == idx), None)
    if match is None:
        raise api_error(404, "Script line not found", "NOT_FOUND")
    if not 0 <= body.best_take_index < len(match["takes"]):
        raise api_error(400, f"Line {idx} has {len(match['takes'])} takes", "INVALID_TAKE")
    await db.alignments.update_one(
        {"_id": alignment["_id"]},
        {"$set": {"matches.$[m].best_take_index": body.best_take_index}},
        array_filters=[{"m.script_line_idx": idx}],
    )
    match["best_take_index"] = body.best_take_index
    return alignment


@router.post("/projects/{project_id}/rough-cut", response_model=Clip)
async def rough_cut(project_id: str, user: dict = Depends(get_current_user)):
    """Best takes in script order as an editable clip (kind=rough_cut). Rebuilding pushes a new EDL version."""
    project = await owned("projects", project_id, user)
    alignment = await db.alignments.find_one({"project_id": project["_id"]})
    if not alignment:
        raise api_error(404, "Project hasn't been processed yet", "ALIGNMENT_NOT_READY")
    edl, now = rough_cut_edl(alignment), utcnow()
    return await db.clips.find_one_and_update(
        {"project_id": project["_id"], "kind": "rough_cut"},
        {
            "$set": {"edl": edl, "source_asset_id": alignment["asset_id"]},
            "$push": {"edl_versions": {"edl": edl, "edited_by": "ai", "at": now}},
            "$setOnInsert": {
                "title": f"{project['title']} (rough cut)", "reason": "Best take of every script line, in script order",
                "scores": {"hook": 0, "completeness": 0, "virality": 0, "overall": 0},
                "render": {"status": None, "url": None, "rendered_at": None},
                "status": "suggested", "created_at": now,
            },
        },
        upsert=True,
        return_document=True,
    )
