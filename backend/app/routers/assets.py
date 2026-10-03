import mimetypes

from bson import ObjectId
from fastapi import APIRouter, BackgroundTasks, Depends, File, Form, Query, UploadFile
from pydantic import BaseModel

from app.db import db, oid, owned
from app.errors import api_error
from app.jobs.runner import create_job, run_job
from app.models.asset import Asset
from app.models.common import utcnow
from app.models.transcript import Transcript
from app.services import media, storage
from app.services.auth import get_current_user
from app.services.pipeline import process_asset
from app.services.search import search as search_assets
from app.services.workflow import advance

router = APIRouter(tags=["assets"])


class UploadOut(BaseModel):
    asset: Asset
    job_id: str | None = None


def _kind(mime: str) -> str:
    major = mime.split("/")[0]
    return major if major in ("video", "audio", "image") else "document"


@router.post("/assets/upload", response_model=UploadOut, status_code=201)
async def upload(
    bg: BackgroundTasks,
    file: UploadFile = File(...),
    project_id: str | None = Form(None),
    user: dict = Depends(get_current_user),
):
    pid = (await owned("projects", project_id, user))["_id"] if project_id else None

    mime = file.content_type
    if not mime or mime == "application/octet-stream":
        mime = mimetypes.guess_type(file.filename or "")[0] or "application/octet-stream"
    kind = _kind(mime)

    asset_id = ObjectId()
    path = await storage.save_upload(file, str(asset_id))
    folder = str(user["_id"])

    meta = {}
    if kind != "document":
        try:
            meta = await media.probe(path)
        except FileNotFoundError:
            path.unlink(missing_ok=True)
            raise api_error(503, "FFmpeg is not installed on the server", "FFMPEG_MISSING")
        except RuntimeError:
            path.unlink(missing_ok=True)
            raise api_error(400, "Could not read this media file", "INVALID_MEDIA")

    url = await storage.publish(path, folder)
    thumb = url if kind == "image" else None
    if kind == "video":
        t = path.parent / "thumb.jpg"
        try:
            await media.run(media.thumbnail_args(path, t, at=min(1.0, (meta.get("duration") or 0) / 2)))
            thumb = await storage.publish(t, folder)
        except RuntimeError:
            pass  # no thumbnail is not worth failing the upload

    doc = {
        "_id": asset_id,
        "user_id": user["_id"],
        "project_id": pid,
        "type": kind,
        "filename": path.name,
        "storage_url": url,
        "thumbnail_url": thumb,
        "mime_type": mime,
        "size_bytes": path.stat().st_size,
        "metadata": meta,
        "ai": {"tags": [], "description": "", "transcript_id": None, "status": "pending"},
        "created_at": utcnow(),
    }
    await db.assets.insert_one(doc)

    if pid and kind == "video":
        await db.projects.update_one(
            {"_id": pid}, {"$addToSet": {"footage_asset_ids": asset_id}, "$set": {"updated_at": utcnow()}}
        )
        await advance(pid, "editing")  # F7: footage is in

    job_id = None
    if kind in ("video", "audio"):
        job_id = await create_job("transcription", user["_id"], pid)
        run_job(bg, job_id, process_asset, str(asset_id))
    return {"asset": doc, "job_id": job_id}


@router.get("/assets", response_model=list[Asset])
async def list_assets(
    type: str | None = None,
    project_id: str | None = None,
    tag: str | None = None,
    user: dict = Depends(get_current_user),
):
    q: dict = {"user_id": user["_id"]}
    if type:
        q["type"] = type
    if project_id:
        q["project_id"] = oid(project_id)
    if tag:
        q["ai.tags"] = tag
    # ponytail: capped at 500, add cursor pagination when a library outgrows it
    return await db.assets.find(q).sort("created_at", -1).to_list(500)


class SearchHit(BaseModel):
    asset: Asset
    start: float | None
    end: float | None
    snippet: str
    score: float
    kind: str
    match: str  # "semantic" (Atlas Vector Search) or "keyword" (text-index fallback)


@router.get("/assets/search", response_model=list[SearchHit])
async def search(q: str = Query(min_length=2, max_length=200), user: dict = Depends(get_current_user)):
    """F1: find the moment a phrase or idea comes up in your footage."""
    return await search_assets(user["_id"], q.strip())


@router.get("/assets/{asset_id}", response_model=Asset)
async def get_asset(asset_id: str, user: dict = Depends(get_current_user)):
    return await owned("assets", asset_id, user)


@router.get("/assets/{asset_id}/transcript", response_model=Transcript)
async def get_transcript(asset_id: str, user: dict = Depends(get_current_user)):
    asset = await owned("assets", asset_id, user)
    transcript = await db.transcripts.find_one({"asset_id": asset["_id"]})
    if not transcript:
        raise api_error(404, "Transcript not ready", "TRANSCRIPT_NOT_READY")
    return transcript
