from typing import Literal

from fastapi import APIRouter, BackgroundTasks, Depends
from pydantic import BaseModel, Field
from pymongo import ReturnDocument

from app.db import db, owned, owned_clip
from app.errors import api_error
from app.jobs.runner import create_job, run_job
from app.models.clip import EDL, Clip
from app.models.common import utcnow
from app.models.generated_content import Platform
from app.services.auth import get_current_user
from app.services.edl import platform_variant, rebuild_from_words
from app.services.pipeline import adapt_clip, clip_context, render_clip
from app.services.reframe import PLATFORMS
from app.services.workflow import advance

router = APIRouter(tags=["clips"])


class StatusIn(BaseModel):
    status: Literal["suggested", "approved", "rejected"]


class AdaptIn(BaseModel):
    platforms: list[Platform] = Field(default_factory=lambda: list(PLATFORMS), min_length=1)


class RenderIn(BaseModel):
    platform: Platform | None = None


async def _update(clip_id, update: dict) -> dict:
    return await db.clips.find_one_and_update({"_id": clip_id}, update, return_document=ReturnDocument.AFTER)


@router.get("/projects/{project_id}/clips", response_model=list[Clip])
async def list_clips(project_id: str, user: dict = Depends(get_current_user)):
    project = await owned("projects", project_id, user)
    return await db.clips.find({"project_id": project["_id"]}).sort("scores.overall", -1).to_list(200)


@router.get("/clips/{clip_id}", response_model=Clip)
async def get_clip(clip_id: str, user: dict = Depends(get_current_user)):
    return await owned_clip(clip_id, user)


@router.put("/clips/{clip_id}/edl", response_model=Clip)
async def save_edl(clip_id: str, body: EDL, user: dict = Depends(get_current_user)):
    """Creator edit: becomes the current EDL and a new version (edited_by user)."""
    clip = await owned_clip(clip_id, user)
    if not body.segments:
        raise api_error(400, "A clip needs at least one segment", "EMPTY_EDL")
    edl = body.model_dump()
    return await _update(clip["_id"], {
        "$set": {"edl": edl},
        "$push": {"edl_versions": {"edl": edl, "edited_by": "user", "at": utcnow()}},
    })


class WordsIn(BaseModel):
    kept: list[float] = Field(min_length=1)  # start times of the words to keep


def _rebuilt_variants(clip: dict, main: dict, words: list[dict]) -> list[dict]:
    """Platform versions follow the main cut; exports made from the old cut are marked stale."""
    return [{**v, "edl": platform_variant(main, PLATFORMS[v["platform"]], words),
             "render": {**v["render"], "status": "stale"} if v["render"].get("url") else v["render"]}
            for v in clip.get("variants", [])]


def clip_source_range(clip: dict) -> tuple[float, float]:
    """The footage a clip may draw words from: the AI's original cut, widened by any later edit."""
    segs = clip["edl_versions"][0]["edl"]["segments"] + clip["edl"]["segments"]
    return min(s["start"] for s in segs), max(s["end"] for s in segs)


@router.put("/clips/{clip_id}/words", response_model=Clip)
async def edit_words(clip_id: str, body: WordsIn, user: dict = Depends(get_current_user)):
    """Transcript editing: delete/restore words and the video follows (Descript-style). Versioned like any edit;
    platform versions are rebuilt from the new cut and their old exports marked stale."""
    clip = await owned_clip(clip_id, user)
    text_, words = await clip_context(clip)
    start, end = clip_source_range(clip)
    try:
        new = rebuild_from_words(clip["edl"], words, {round(t, 3) for t in body.kept}, start, end)
    except ValueError as e:
        raise api_error(400, str(e), "EMPTY_EDL")
    return await _update(clip["_id"], {
        "$set": {"edl": new, "variants": _rebuilt_variants(clip, new, words)},
        "$push": {"edl_versions": {"edl": new, "edited_by": "user", "at": utcnow()}},
    })


@router.post("/clips/{clip_id}/undo", response_model=Clip)
async def undo(clip_id: str, user: dict = Depends(get_current_user)):
    """Drop the latest version and restore the one before it. The first AI version can't be undone."""
    clip = await owned_clip(clip_id, user)
    if len(clip["edl_versions"]) < 2:
        raise api_error(400, "Nothing to undo", "NOTHING_TO_UNDO")
    previous = clip["edl_versions"][-2]["edl"]
    _, words = await clip_context(clip)
    return await _update(clip["_id"], {
        "$set": {"edl": previous, "variants": _rebuilt_variants(clip, previous, words)},
        "$pop": {"edl_versions": 1},
    })


@router.patch("/clips/{clip_id}/status", response_model=Clip)
async def set_status(clip_id: str, body: StatusIn, user: dict = Depends(get_current_user)):
    clip = await owned_clip(clip_id, user)
    if body.status == "approved":
        await advance(clip["project_id"], "review")  # F7
    return await _update(clip["_id"], {"$set": {"status": body.status}})


@router.post("/clips/{clip_id}/adapt", status_code=202)
async def adapt(clip_id: str, body: AdaptIn, bg: BackgroundTasks, user: dict = Depends(get_current_user)):
    """F6: per-platform EDL variants (aspect, captions, length, face-tracked crop) + per-platform copy."""
    clip = await owned_clip(clip_id, user)
    job_id = await create_job("adapt", user["_id"], clip["project_id"])
    run_job(bg, job_id, adapt_clip, str(clip["_id"]), list(dict.fromkeys(body.platforms)))
    return {"job_id": job_id}


@router.post("/clips/{clip_id}/render", status_code=202)
async def render(clip_id: str, bg: BackgroundTasks, body: RenderIn = RenderIn(), user: dict = Depends(get_current_user)):
    """Render the clip (or one platform variant) to MP4. Result URL lands in clip.render / variant.render."""
    clip = await owned_clip(clip_id, user)
    if body.platform and not any(v["platform"] == body.platform for v in clip.get("variants", [])):
        raise api_error(400, f"No {body.platform} version yet. Adapt the clip first.", "NO_VARIANT")
    job_id = await create_job("render", user["_id"], clip["project_id"])
    run_job(bg, job_id, render_clip, str(clip["_id"]), body.platform)
    return {"job_id": job_id}
