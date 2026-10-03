"""Load one complete demo project so the app looks full on start.

Runs the REAL pipeline on a video (transcribe, tag, index, align, find clips, build edits, reframe),
then hooks, adapt-for-all and renders, plus a few kanban cards. Only the analytics are mock (# MOCK:).

    cd backend
    python -m scripts.seed_demo                              # sample footage in demo/
    python -m scripts.seed_demo --video my_take.mp4 --script my_script.txt

Re-running wipes and rebuilds the demo account (only that account). Uses ~8 Gemini calls.
"""

import argparse
import asyncio
import shutil
import sys
import time
from pathlib import Path

from bson import ObjectId

from app.db import create_indexes, db, ping
from app.jobs.runner import create_job, execute
from app.models.common import utcnow
from app.routers.clips import StatusIn, set_status
from app.routers.generate import HooksIn, SelectIn, generate_hooks, select_variant
from app.services import insights, media, reframe, storage, workflow
from app.services.auth import hash_password
from app.services.pipeline import adapt_clip, process_asset, render_clip, run_pipeline
from app.services.reframe import PLATFORMS
from app.services.scripts import ensure_tone_profile, label_sections, parse_lines

DEMO = Path(__file__).resolve().parents[1] / "demo"
TITLE = "Why cutting coffee won't make you rich"
KANBAN = [  # extra cards so the board shows a real pipeline of work
    ("Credit cards are not the enemy", "idea"),
    ("The rent rule nobody tells you", "scripting"),
    ("3 money mistakes I made at 22", "recording"),
]
RENDER_PLATFORMS = ["shorts", "linkedin"]


def step(msg: str) -> float:
    print(f"\n> {msg}", flush=True)
    return time.perf_counter()


def done(t0: float, extra: str = "") -> None:
    print(f"  done in {time.perf_counter() - t0:.1f}s {extra}", flush=True)


async def wipe(user_id: ObjectId) -> None:
    """Remove everything the demo account owns (DB docs + media files)."""
    projects = [p["_id"] for p in await db.projects.find({"user_id": user_id}, {"_id": 1}).to_list(1000)]
    assets = [a["_id"] for a in await db.assets.find({"user_id": user_id}, {"_id": 1}).to_list(1000)]
    for coll, q in [
        ("clips", {"project_id": {"$in": projects}}), ("alignments", {"project_id": {"$in": projects}}),
        ("scripts", {"user_id": user_id}), ("generated_content", {"user_id": user_id}), ("analytics", {"user_id": user_id}),
        ("jobs", {"user_id": user_id}), ("transcripts", {"asset_id": {"$in": assets}}), ("embeddings", {"user_id": user_id}),
        ("assets", {"user_id": user_id}), ("projects", {"user_id": user_id}),
    ]:
        await db[coll].delete_many(q)
    for a in assets:
        shutil.rmtree(storage.MEDIA_DIR / "assets" / str(a), ignore_errors=True)
    await db.users.update_one({"_id": user_id}, {"$set": {"tone_profile": ""}})


async def run_job(kind: str, user_id, project_id, fn, *args) -> dict:
    job_id = await create_job(kind, user_id, project_id)
    await execute(job_id, fn, *args)
    job = await db.jobs.find_one({"_id": ObjectId(job_id)})
    if job["status"] != "done":
        sys.exit(f"  {kind} job failed: {job['error']}")
    return job


async def main(args) -> None:
    if not await ping():
        sys.exit("MongoDB unreachable: check MONGODB_URI in backend/.env")
    await create_indexes()
    video, script_text = Path(args.video), Path(args.script).read_text(encoding="utf-8")
    if not video.exists():
        sys.exit(f"No video at {video}")

    t0 = step(f"Demo account {args.email}")
    user = await db.users.find_one({"email": args.email})
    if user:
        await wipe(user["_id"])
    else:
        uid = (await db.users.insert_one({
            "name": "Aarav Mehta", "email": args.email, "password_hash": hash_password(args.password),
            "niche": "personal finance", "tone_profile": "", "connected_platforms": [], "created_at": utcnow(),
        })).inserted_id
        user = await db.users.find_one({"_id": uid})
    uid = user["_id"]
    done(t0, "(previous demo data wiped)")

    for title, stage in KANBAN:
        now = utcnow()
        pid = (await db.projects.insert_one({
            "user_id": uid, "title": title, "idea": "", "stage": "idea", "stage_history": [{"stage": "idea", "at": now}],
            "script_id": None, "footage_asset_ids": [], "target_platforms": ["shorts", "reels"], "scheduled_for": None,
            "published_at": None, "tags": [], "created_at": now, "updated_at": now})).inserted_id
        if stage != "idea":
            await workflow.set_stage(pid, stage)

    t0 = step("Project + script (Gemini labels each line's section)")
    now = utcnow()
    pid = (await db.projects.insert_one({
        "user_id": uid, "title": TITLE, "idea": "Debunk the coffee myth with a personal story", "stage": "idea",
        "stage_history": [{"stage": "idea", "at": now}], "script_id": None, "footage_asset_ids": [],
        "target_platforms": list(PLATFORMS), "scheduled_for": None, "published_at": None, "tags": ["finance"],
        "created_at": now, "updated_at": now})).inserted_id
    lines = parse_lines(script_text)
    sections = await label_sections(lines)
    sid = (await db.scripts.insert_one({
        "user_id": uid, "project_id": pid, "title": TITLE, "content": script_text,
        "lines": [{"idx": i, "text": t, "section": s} for i, (t, s) in enumerate(zip(lines, sections))],
        "source": "user", "version": 1, "created_at": utcnow()})).inserted_id
    await db.projects.update_one({"_id": pid}, {"$set": {"script_id": sid}})
    await workflow.advance(pid, "recording")
    done(t0, f"({len(lines)} lines)")

    t0 = step(f"Footage: {video.name}")
    aid = ObjectId()
    path = storage.asset_dir(str(aid)) / storage.safe_name(video.name)
    shutil.copyfile(video, path)
    meta = await media.probe(path)
    thumb = path.parent / "thumb.jpg"
    await media.run(media.thumbnail_args(path, thumb, at=min(1.0, (meta.get("duration") or 0) / 2)))
    await db.assets.insert_one({
        "_id": aid, "user_id": uid, "project_id": pid, "type": "video", "filename": path.name,
        "storage_url": await storage.publish(path, str(uid)), "thumbnail_url": await storage.publish(thumb, str(uid)),
        "mime_type": "video/mp4", "size_bytes": path.stat().st_size, "metadata": meta,
        "ai": {"tags": [], "description": "", "keyframes": [], "transcript_id": None, "status": "pending"}, "created_at": utcnow()})
    await db.projects.update_one({"_id": pid}, {"$addToSet": {"footage_asset_ids": aid}})
    await workflow.advance(pid, "editing")
    done(t0, f"({meta.get('duration', 0):.0f}s, {meta.get('width')}x{meta.get('height')})")

    t0 = step("Transcribe + describe + index (upload job)")
    await run_job("transcription", uid, pid, process_asset, str(aid))
    done(t0)

    t0 = step("Align script, find clips, build edits, track speaker (pipeline job)")
    await run_job("pipeline", uid, pid, run_pipeline, str(pid))
    alignment = await db.alignments.find_one({"project_id": pid})
    clips = await db.clips.find({"project_id": pid, "kind": "short"}).sort("scores.overall", -1).to_list(20)
    done(t0, f"(coverage {alignment['coverage']:.0%}, {len(clips)} clips)")
    if not clips:
        sys.exit("  No clips found: the footage needs 15-60s self-contained moments.")
    top = clips[0]

    t0 = step(f"Hooks for top clip: {top['title']!r}")
    hooks = await generate_hooks(HooksIn(clip_id=str(top["_id"])), user)
    await select_variant(str(hooks["_id"]), SelectIn(variant_index=0), user)
    for c in clips[:2]:
        await set_status(str(c["_id"]), StatusIn(status="approved"), user)
    done(t0, f"(selected: {hooks['variants'][0]['text']!r})")

    t0 = step("Adapt for all platforms (reframe + per-platform copy)")
    await run_job("adapt", uid, pid, adapt_clip, str(top["_id"]), list(PLATFORMS))
    done(t0)

    for platform in RENDER_PLATFORMS:
        t0 = step(f"Render {platform}")
        job = await run_job("render", uid, pid, render_clip, str(top["_id"]), platform)
        done(t0, f"(job {(job['finished_at'] - job['created_at']).total_seconds():.1f}s)")

    t0 = step("Tone profile + sample analytics (MOCK)")
    await ensure_tone_profile(user)
    await insights.seed_mock_analytics(uid)
    done(t0)

    reframe.close_detector()
    print(f"\nDemo ready. Sign in as {args.email} / {args.password}")
    print(f"Project: http://localhost:5173/projects/{pid}")
    print(f"Top clip: http://localhost:5173/clips/{top['_id']}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--video", default=str(DEMO / "demo.mp4"))
    parser.add_argument("--script", default=str(DEMO / "script.txt"))
    parser.add_argument("--email", default="demo@creatorai.dev")
    parser.add_argument("--password", default="demo-pass-2026")
    asyncio.run(main(parser.parse_args()))
