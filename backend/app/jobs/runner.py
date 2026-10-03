"""Background jobs: a `jobs` doc tracks status; work runs in FastAPI BackgroundTasks.

Usage in a route:
    job_id = await create_job("pipeline", user["_id"], project_id)
    run_job(background_tasks, job_id, run_pipeline, project_id)
    return {"job_id": job_id}

The work function receives job_id first so it can call update_job(job_id, step=..., progress=...).
"""

import logging
from typing import Any, Awaitable, Callable

from bson import ObjectId
from fastapi import BackgroundTasks

from app.db import db
from app.errors import describe
from app.models.common import utcnow

log = logging.getLogger("uvicorn.error")


async def create_job(type: str, user_id: str | ObjectId, project_id: str | ObjectId | None = None) -> str:
    res = await db.jobs.insert_one({
        "user_id": ObjectId(user_id),
        "project_id": ObjectId(project_id) if project_id else None,
        "type": type,
        "status": "queued",
        "current_step": "",
        "progress": 0,
        "error": None,
        "created_at": utcnow(),
        "finished_at": None,
    })
    return str(res.inserted_id)


async def update_job(job_id: str, *, step: str | None = None, progress: int | None = None) -> None:
    fields: dict[str, Any] = {}
    if step is not None:
        fields["current_step"] = step
    if progress is not None:
        fields["progress"] = progress
    # Only running jobs: a late progress callback must not touch a finished job.
    await db.jobs.update_one({"_id": ObjectId(job_id), "status": "running"}, {"$set": fields})


async def finish_job(job_id: str) -> None:
    await db.jobs.update_one(
        {"_id": ObjectId(job_id)},
        {"$set": {"status": "done", "progress": 100, "finished_at": utcnow()}},
    )


async def fail_job(job_id: str, error: str) -> None:
    await db.jobs.update_one(
        {"_id": ObjectId(job_id)},
        {"$set": {"status": "failed", "error": error, "finished_at": utcnow()}},
    )


async def execute(job_id: str, fn: Callable[..., Awaitable[Any]], *args: Any) -> None:
    """Run `await fn(job_id, *args)` now, recording running / done / failed on the job."""
    await db.jobs.update_one({"_id": ObjectId(job_id)}, {"$set": {"status": "running"}})
    try:
        await fn(job_id, *args)
    except Exception as e:
        log.exception("job %s failed", job_id)
        await fail_job(job_id, describe(e))
    else:
        await finish_job(job_id)


def run_job(bg: BackgroundTasks, job_id: str, fn: Callable[..., Awaitable[Any]], *args: Any) -> None:
    """Schedule `await fn(job_id, *args)` after the response is sent."""
    bg.add_task(execute, job_id, fn, *args)
