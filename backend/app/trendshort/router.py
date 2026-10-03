"""Trend-to-Short API, mounted at /api/v1/t2s. Every route is scoped to the signed-in CreatorAi user.

Runs live in the feature's own SQLite store (stage records, caches, EDL overrides); a finished Short is
copied into CreatorAi (asset + script + project) by POST /runs/{id}/save.
"""
from __future__ import annotations

import asyncio
import json
import shutil
from pathlib import Path

from bson import ObjectId
from fastapi import APIRouter, Depends, Query
from fastapi.responses import FileResponse
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from pydantic import BaseModel
from sse_starlette.sse import EventSourceResponse

from app.db import db as mongo
from app.errors import api_error
from app.models.common import utcnow
from app.services import media as cmedia
from app.services import storage
from app.services.auth import get_current_user

from . import orchestrator
from .agents import trend_agent
from .config import MissingConfig, find_tool, settings
from .db import init_db
from .events import bus
from .logging_setup import setup_logging
from .providers import captions, footage, llm, publish as yt, trends as trend_providers, tts
from .schemas import EDL, PublishRequest, RunCreate, ScriptPatch, VisualSwap
from .state_machine import STAGES

setup_logging()
init_db()

router = APIRouter(prefix="/t2s", tags=["trend-to-short"])
_bearer = HTTPBearer(auto_error=False)


async def user_header_or_query(
    cred: HTTPAuthorizationCredentials | None = Depends(_bearer),
    token: str | None = Query(None, include_in_schema=False),
) -> dict:
    """EventSource can't send headers, so the SSE route also accepts ?token=."""
    if cred is None and token:
        cred = HTTPAuthorizationCredentials(scheme="Bearer", credentials=token)
    return await get_current_user(cred)


def _owned(run_id: str, user: dict) -> dict:
    r = orchestrator.get_run(run_id)
    if not r or r.get("user_id") != str(user["_id"]):
        raise api_error(404, "Run not found", "NOT_FOUND")
    return r


@router.get("/config")
def config(user: dict = Depends(get_current_user)) -> dict:
    return {"mock_mode": settings.mock_mode, "stages": STAGES,
            "publish_targets": [
                {"id": "youtube", "label": "YouTube Shorts", "kind": "real", "configured": yt.youtube_configured()[0],
                 "notice": yt.UNVERIFIED_NOTICE},
                {"id": "export", "label": "TikTok / Instagram package", "kind": "export-only",
                 "notice": "Creates mp4 + .srt + metadata.json. Not posted automatically."}]}


@router.get("/trends")
async def get_trends(region: str = "US", category: str | None = None, refresh: bool = False,
                     user: dict = Depends(get_current_user)) -> dict:
    return await trend_agent.get_trends(region=region, category=category or None, refresh=refresh)


@router.get("/runs")
def list_runs(user: dict = Depends(get_current_user)) -> list[dict]:
    return [{**r, "busy": orchestrator.is_busy(r["id"])} for r in orchestrator.list_runs(str(user["_id"]))]


@router.post("/runs", status_code=201)
async def create_run(body: RunCreate, user: dict = Depends(get_current_user)) -> dict:
    idea = trend_agent.get_idea(body.trend_id)
    if idea is None:
        raise api_error(404, "That trend has expired. Refresh the trend feed and pick it again.", "TREND_NOT_FOUND")
    run = orchestrator.create_run(idea, body.mode, body.voice_profile, user_id=str(user["_id"]))
    orchestrator.start(run["id"])
    return run


@router.get("/runs/{run_id}")
def get_run(run_id: str, user: dict = Depends(get_current_user)) -> dict:
    return {**_owned(run_id, user), "busy": orchestrator.is_busy(run_id)}


@router.get("/runs/{run_id}/events")
async def run_events(run_id: str, user: dict = Depends(user_header_or_query)):
    _owned(run_id, user)

    async def gen():
        q = bus.subscribe(run_id)
        try:
            yield {"event": "snapshot", "data": json.dumps({"run": orchestrator.get_run(run_id)}, default=str)}
            while True:
                try:
                    msg = await asyncio.wait_for(q.get(), timeout=15)
                    yield {"event": msg["event"], "data": json.dumps(msg, default=str)}
                except asyncio.TimeoutError:
                    yield {"event": "ping", "data": "{}"}
        finally:
            bus.unsubscribe(run_id, q)
    return EventSourceResponse(gen())


@router.get("/runs/{run_id}/log")
def run_log(run_id: str, tail: int = 200, user: dict = Depends(get_current_user)) -> dict:
    _owned(run_id, user)
    p = settings.runs_dir / run_id / "run.log"
    lines = p.read_text(encoding="utf-8").splitlines()[-tail:] if p.exists() else []
    return {"lines": [json.loads(x) for x in lines if x.strip()]}


@router.post("/runs/{run_id}/approve")
async def approve(run_id: str, user: dict = Depends(get_current_user)) -> dict:
    _owned(run_id, user)
    return orchestrator.approve(run_id)


class ModeBody(BaseModel):
    mode: str


@router.post("/runs/{run_id}/mode")
async def set_mode(run_id: str, body: ModeBody, user: dict = Depends(get_current_user)) -> dict:
    _owned(run_id, user)
    if body.mode not in ("review", "auto"):
        raise api_error(422, "mode must be review or auto", "INVALID_MODE")
    return orchestrator.set_mode(run_id, body.mode)


@router.patch("/runs/{run_id}/script")
def patch_script(run_id: str, body: ScriptPatch, user: dict = Depends(get_current_user)) -> dict:
    _owned(run_id, user)
    return orchestrator.patch_script(run_id, body.script)


@router.patch("/runs/{run_id}/edl")
async def patch_edl(run_id: str, edl: EDL, user: dict = Depends(get_current_user)) -> dict:
    _owned(run_id, user)
    try:
        return orchestrator.patch_edl(run_id, edl)
    except ValueError as e:
        raise api_error(409, str(e), "CONFLICT")


@router.patch("/runs/{run_id}/visuals")
async def patch_visuals(run_id: str, body: VisualSwap, user: dict = Depends(get_current_user)) -> dict:
    _owned(run_id, user)
    try:
        return await orchestrator.apply_visual_swap(run_id, body)
    except ValueError as e:
        raise api_error(422, str(e), "INVALID_SWAP")


@router.post("/runs/{run_id}/stages/{stage}/rerun")
async def rerun(run_id: str, stage: str, user: dict = Depends(get_current_user)) -> dict:
    _owned(run_id, user)
    if orchestrator.is_busy(run_id):
        raise api_error(409, "Run is busy; wait for the current stage to finish.", "RUN_BUSY")
    try:
        return orchestrator.rerun(run_id, stage)
    except (ValueError, RuntimeError) as e:
        raise api_error(409, str(e), "CONFLICT")


@router.post("/runs/{run_id}/publish")
async def publish(run_id: str, req: PublishRequest, user: dict = Depends(get_current_user)) -> dict:
    _owned(run_id, user)
    try:
        return (await orchestrator.publish(run_id, req)).model_dump(mode="json")
    except MissingConfig as e:
        raise api_error(400, str(e), "MISSING_CONFIG")
    except ValueError as e:
        raise api_error(409, str(e), "CONFLICT")


def _script_doc(script: dict, user_id: ObjectId, project_id: ObjectId) -> dict:
    scenes = script.get("scenes", [])
    lines = [{"idx": i, "text": s["narration"],
              "section": "hook" if i == 0 else "cta" if i == len(scenes) - 1 else "body"}
             for i, s in enumerate(scenes)]
    return {"user_id": user_id, "project_id": project_id, "title": script.get("title", ""),
            "content": "\n".join(line["text"] for line in lines), "lines": lines,
            "source": "ai_generated", "version": 1, "created_at": utcnow()}


@router.post("/runs/{run_id}/save")
async def save_to_creatorai(run_id: str, user: dict = Depends(get_current_user)) -> dict:
    """Copy the finished Short into CreatorAi: a Library video asset, an AI script, and a project at
    the "review" stage that links both. Idempotent: a second call returns the same project."""
    run = _owned(run_id, user)
    if run.get("project_id"):
        return {"project_id": run["project_id"], "created": False}
    asm, scr = run["stages"].get("assembly", {}), run["stages"].get("script", {})
    if asm.get("status") != "done" or not (asm.get("output") or {}).get("video_path"):
        raise api_error(409, "Render the video before saving it to CreatorAi.", "NOT_RENDERED")
    script = scr.get("output") or {}
    src = Path(asm["output"]["video_path"])
    if not src.is_file():
        raise api_error(409, "The rendered video file is missing. Re-render the video and try again.", "FILE_MISSING")

    now, uid = utcnow(), user["_id"]
    asset_id, project_id = ObjectId(), ObjectId()
    dst = storage.asset_dir(str(asset_id)) / storage.safe_name(f"{script.get('title') or 'short'}.mp4")
    await asyncio.to_thread(shutil.copyfile, src, dst)
    folder = str(uid)
    try:
        meta = await cmedia.probe(dst)
    except RuntimeError:
        meta = {}
    url = await storage.publish(dst, folder)
    thumb = None
    try:
        t = dst.parent / "thumb.jpg"
        await cmedia.run(cmedia.thumbnail_args(dst, t, at=min(1.0, (meta.get("duration") or 0) / 2)))
        thumb = await storage.publish(t, folder)
    except RuntimeError:
        pass

    tags = [h.lstrip("#").lower() for h in script.get("hashtags", []) if h.strip("#")]
    await mongo.assets.insert_one({
        "_id": asset_id, "user_id": uid, "project_id": project_id, "type": "video", "filename": dst.name,
        "storage_url": url, "thumbnail_url": thumb, "mime_type": "video/mp4", "size_bytes": dst.stat().st_size,
        "metadata": meta,
        # The script is already known, so the asset is "ready" without re-transcribing it.
        "ai": {"tags": [*tags, "trend-to-short"], "description": script.get("description", ""),
               "keyframes": [], "transcript_id": None, "status": "ready"},
        "created_at": now,
    })
    script_id = (await mongo.scripts.insert_one(_script_doc(script, uid, project_id))).inserted_id
    idea = run["idea"]
    await mongo.projects.insert_one({
        "_id": project_id, "user_id": uid, "title": script.get("title") or idea["title"],
        "idea": f"{idea['hook_angle']}\n\nWhy it's trending: {idea['why_trending']}",
        "stage": "review",
        "stage_history": [{"stage": s, "at": now} for s in ("idea", "scripting", "editing", "review")],
        "script_id": script_id, "footage_asset_ids": [asset_id],
        "target_platforms": ["shorts", "reels", "tiktok"], "scheduled_for": None, "published_at": None,
        "tags": ["trend-to-short", *tags[:5]], "created_at": now, "updated_at": now,
    })
    orchestrator.set_project(run_id, str(project_id))
    return {"project_id": str(project_id), "asset_id": str(asset_id), "created": True}


@router.get("/health/providers")
async def health(user: dict = Depends(get_current_user)) -> dict:
    async def llm_status(p):
        ok, why = p.configured()
        return {"name": p.name, "kind": "llm", "status": await p.ping(), "detail": "" if ok else why,
                "in_chain": p in llm.chain()}
    llms = await asyncio.gather(*(llm_status(p) for p in llm.all_providers()))

    def simple(kind, items, chain):
        out = []
        for p in items:
            ok, why = p.configured()
            out.append({"name": p.name, "kind": kind,
                        "status": "available" if ok else ("missing_key" if "key" in why.lower() else "not_configured"),
                        "detail": why if not ok else "", "in_chain": p in chain})
        return out
    w_ok, w_why = captions.whisper_available()
    y_ok, y_why = yt.youtube_configured()
    tp = trend_providers.all_providers()
    enabled_tp = {p.name for p in trend_providers.providers()}
    ff_ok = bool(find_tool("ffmpeg") and find_tool("ffprobe"))
    rows = (list(llms) + simple("tts", tts.all_providers(), tts.chain()) +
            simple("footage", footage.all_providers(), footage.chain()) +
            simple("trends", tp, [p for p in tp if p.name in enabled_tp]) +
            [{"name": "faster-whisper", "kind": "captions", "status": "available" if w_ok else "not_configured",
              "detail": w_why, "in_chain": True},
             {"name": "youtube-upload", "kind": "publish", "status": "available" if y_ok else "not_configured",
              "detail": y_why, "in_chain": True},
             {"name": "ffmpeg", "kind": "media", "status": "available" if ff_ok else "missing",
              "detail": "" if ff_ok else "install FFmpeg (winget install Gyan.FFmpeg) or set FFMPEG_DIR",
              "in_chain": True}])
    from .ratelimit import _limiters
    for r in rows:
        if r["name"] in _limiters and _limiters[r["name"]].is_rate_limited:
            r["status"] = "rate_limited"
    return {"mock_mode": settings.mock_mode, "providers": rows}


# Public like CreatorAi's /media mount (a <video>/<audio> tag can't send a bearer token), but restricted to
# generated media and the demo asset set, never arbitrary paths.
files_router = APIRouter(prefix="/t2s", tags=["trend-to-short"])


@files_router.get("/files")
def files(path: str = Query(...)) -> FileResponse:
    p = Path(path).resolve()
    allowed = [settings.data_dir.resolve(), settings.demo_assets.resolve()]
    if not any(p.is_relative_to(a) for a in allowed) or not p.is_file():
        raise api_error(404, "File not found", "NOT_FOUND")
    return FileResponse(p)
