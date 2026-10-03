"""Background pipelines.

process_asset: one upload -> keyframes, audio, transcript, vision tags (pipeline steps 2-4).
run_pipeline: one project -> transcription -> tagging -> alignment -> clip finding (steps 1-7).
"""

import logging

from bson import ObjectId
from pymongo import ReturnDocument

from app.db import db
from app.jobs.runner import update_job
from app.models.common import utcnow
from app.services import alignment, clip_finder, edl, llm, media, reframe, renderer, scripts, search, storage, tagging, workflow
from app.services.storage import asset_dir
from app.services.transcription import sentences, transcribe

log = logging.getLogger("uvicorn.error")


async def _tag(asset_id: str) -> None:
    """Vision tags are nice-to-have; never fail a job over them."""
    try:
        await tagging.tag_asset(asset_id)
    except Exception:
        log.warning("Tagging failed for asset %s", asset_id, exc_info=True)


async def process_asset(job_id: str, asset_id: str, lo: int = 0, hi: int = 100) -> None:
    """Progress is reported inside [lo, hi] so a parent pipeline can embed this."""
    def pct(p: int) -> int:
        return lo + (hi - lo) * p // 100

    oid = ObjectId(asset_id)
    asset = await db.assets.find_one({"_id": oid})
    await db.assets.update_one({"_id": oid}, {"$set": {"ai.status": "processing"}})
    try:
        work = asset_dir(asset_id)
        src = work / asset["filename"]

        if asset["type"] == "video":
            await update_job(job_id, step="extracting_keyframes", progress=pct(5))
            (work / "keyframes").mkdir(exist_ok=True)
            await media.run(media.keyframes_args(src, work / "keyframes"))

        await update_job(job_id, step="extracting_audio", progress=pct(10))
        audio = work / "audio.wav"
        await media.run(media.extract_audio_args(src, audio))

        await update_job(job_id, step="transcribing", progress=pct(15))
        last = pct(15)

        async def on_progress(frac: float) -> None:
            nonlocal last
            p = pct(15 + int(frac * 70))
            if p >= last + 5:
                last = p
                await update_job(job_id, progress=p)

        result = await transcribe(audio, asset["metadata"].get("duration"), on_progress)

        await update_job(job_id, step="saving", progress=pct(88))
        saved = await db.transcripts.find_one_and_replace(
            {"asset_id": oid},
            {"asset_id": oid, **result, "created_at": utcnow()},
            upsert=True,
            return_document=ReturnDocument.AFTER,
        )
        await db.assets.update_one({"_id": oid}, {"$set": {"ai.status": "ready", "ai.transcript_id": saved["_id"]}})
    except Exception:
        await db.assets.update_one({"_id": oid}, {"$set": {"ai.status": "failed"}})
        raise

    if asset["type"] == "video":
        await update_job(job_id, step="tagging", progress=pct(92))
        await _tag(asset_id)
    await update_job(job_id, step="indexing", progress=pct(96))
    try:
        await search.index_asset(oid)
    except Exception:
        log.warning("Search indexing failed for asset %s", asset_id, exc_info=True)


async def run_pipeline(job_id: str, project_id: str) -> None:
    pid = ObjectId(project_id)
    project = await db.projects.find_one({"_id": pid})
    script = await db.scripts.find_one({"_id": project["script_id"]})
    asset_id = project["footage_asset_ids"][-1]  # ponytail: aligns the latest footage only; per-asset alignment for multi-file shoots

    # Reuse cached transcript / tags (rule 5); only compute what's missing.
    if not await db.transcripts.find_one({"asset_id": asset_id}, {"_id": 1}):
        await process_asset(job_id, str(asset_id), 0, 60)
    elif not (await db.assets.find_one({"_id": asset_id}))["ai"].get("keyframes"):
        await update_job(job_id, step="tagging", progress=40)
        await _tag(str(asset_id))

    await update_job(job_id, step="aligning", progress=65)
    transcript = await db.transcripts.find_one({"asset_id": asset_id})
    asset = await db.assets.find_one({"_id": asset_id})
    result = await alignment.align(script["lines"], transcript["segments"], llm.embed)
    alignment.attach_visuals(result, asset["ai"].get("keyframes", []))
    await db.alignments.find_one_and_replace(
        {"project_id": pid},
        {"project_id": pid, "script_id": script["_id"], "asset_id": asset_id, **result, "created_at": utcnow()},
        upsert=True,
    )

    await update_job(job_id, step="finding_clips", progress=75)
    await _find_clips(job_id, project, asset, transcript, result)


async def _find_clips(job_id: str, project: dict, asset: dict, transcript: dict, align_result: dict) -> None:
    """F4 + F5: candidate clips -> EDLs -> `clips` (status suggested, first version edited_by ai)."""
    pid = project["_id"]
    # Re-processing replaces untouched AI suggestions; clips the creator approved, rejected or edited stay,
    # and new suggestions may not overlap them.
    await db.clips.delete_many({"project_id": pid, "kind": "short", "status": "suggested",
                                "edl_versions.edited_by": {"$ne": "user"}})
    taken = [(c["edl"]["segments"][0]["start"], c["edl"]["segments"][-1]["end"])
             async for c in db.clips.find({"project_id": pid, "kind": "short"}, {"edl.segments": 1})
             if c["edl"]["segments"]]

    words = [w for s in transcript["segments"] for w in s["words"]]
    sents = sentences(words)
    user = await db.users.find_one({"_id": project["user_id"]}, {"niche": 1, "tone_profile": 1}) or {}
    audio = asset_dir(str(asset["_id"])) / "audio.wav"
    found = await clip_finder.find_clips(
        sents, words, asset["metadata"].get("duration"), audio if audio.exists() else None,
        niche=user.get("niche", ""), tone=await scripts.ensure_tone_profile(user) if user else "",
        adlibs=align_result["unscripted_ranges"], taken=taken,
    )

    await update_job(job_id, step="building_edls", progress=88)
    emphasis = await clip_finder.pick_emphasis(found, sents)
    now, docs = utcnow(), []
    for c, (emph_words, zoom_sents) in zip(found, emphasis):
        clip_edl = edl.build_edl(words, c["start"], c["end"], align_result, emph_words, zoom_sents)
        if not clip_edl["segments"]:
            continue
        docs.append({
            "project_id": pid, "source_asset_id": asset["_id"], "kind": "short",
            "title": c["title"], "reason": c["reason"], "scores": c["scores"],
            "edl": clip_edl, "edl_versions": [{"edl": clip_edl, "edited_by": "ai", "at": now}],
            "render": {"status": None, "url": None, "rendered_at": None},
            "status": "suggested", "created_at": now,
        })
    if docs:
        await db.clips.insert_many(docs)


# ---------- F2 / F6: platform copy, adapt, render ----------

COPY_TYPES = ("title", "caption", "hashtags", "description", "thumbnail_text")


async def clip_context(clip: dict) -> tuple[str, list[dict]]:
    """The clip's spoken text (from its captions) and the source transcript words."""
    transcript = await db.transcripts.find_one({"asset_id": clip["source_asset_id"]}, {"segments.words": 1})
    words = [w for s in transcript["segments"] for w in s["words"]] if transcript else []
    text = " ".join(c["text"] for c in clip["edl"]["captions"]) or " ".join(
        w["w"] for w in words if any(s["start"] <= w["start"] and w["end"] <= s["end"] for s in clip["edl"]["segments"]))
    return text, words


async def save_platform_copy(clip: dict, user_id, copyset: llm.CopySet) -> list[dict]:
    """One generated_content doc per (platform, type); regenerating replaces that platform's copy."""
    docs, now = [], utcnow()
    for pc in copyset.platforms:
        if pc.platform not in reframe.PLATFORMS:
            continue
        values = {"title": pc.title, "caption": pc.caption, "hashtags": " ".join(pc.hashtags),
                  "description": pc.description, "thumbnail_text": pc.thumbnail_text}
        await db.generated_content.delete_many({"clip_id": clip["_id"], "platform": pc.platform, "type": {"$in": COPY_TYPES}})
        docs += [{"user_id": user_id, "project_id": clip["project_id"], "clip_id": clip["_id"], "type": t,
                  "platform": pc.platform, "variants": [{"text": values[t], "selected": True, "score": None, "label": None}],
                  "prompt_context": clip["title"], "created_at": now} for t in COPY_TYPES]
    if docs:
        await db.generated_content.insert_many(docs)
    return docs


async def adapt_clip(job_id: str, clip_id: str, platforms: list[str]) -> None:
    """F6: smart-reframe crop track (once per clip) + per-platform EDL variants + per-platform copy."""
    cid = ObjectId(clip_id)
    clip = await db.clips.find_one({"_id": cid})
    asset = await db.assets.find_one({"_id": clip["source_asset_id"]})
    project = await db.projects.find_one({"_id": clip["project_id"]}, {"user_id": 1})
    user = await db.users.find_one({"_id": project["user_id"]})
    text, words = await clip_context(clip)
    main = clip["edl"]

    if not main["crop_track"] and any(reframe.PLATFORMS[p]["aspect"] != "16:9" for p in platforms):
        await update_job(job_id, step="reframing", progress=10)
        m = asset["metadata"]
        track = await reframe.crop_track(asset_dir(str(asset["_id"])) / asset["filename"], main["segments"], m["width"], m["height"])
        main = {**main, "crop_track": track}
        await db.clips.update_one({"_id": cid}, {"$set": {"edl": main},
                                                 "$push": {"edl_versions": {"edl": main, "edited_by": "ai", "at": utcnow()}}})

    await update_job(job_id, step="writing_copy", progress=55)
    tone = await scripts.ensure_tone_profile(user)
    await save_platform_copy(clip, user["_id"], await llm.platform_copy(text, platforms, user.get("niche", ""), tone))

    await update_job(job_id, step="building_variants", progress=90)
    new = {p: {"platform": p, "edl": edl.platform_variant(main, reframe.PLATFORMS[p], words),
               "render": {"status": None, "url": None, "rendered_at": None}} for p in platforms}
    kept = [v for v in clip.get("variants", []) if v["platform"] not in new]
    await db.clips.update_one({"_id": cid}, {"$set": {"variants": kept + list(new.values())}})


async def render_clip(job_id: str, clip_id: str, platform: str | None) -> None:
    """EDL -> MP4. Main clip EDL, or a platform variant's. Result URL lands in that render block."""
    cid = ObjectId(clip_id)
    clip = await db.clips.find_one({"_id": cid})
    asset = await db.assets.find_one({"_id": clip["source_asset_id"]})
    edl_doc = next(v["edl"] for v in clip["variants"] if v["platform"] == platform) if platform else clip["edl"]
    field = "variants.$[v].render" if platform else "render"
    filters = [{"v.platform": platform}] if platform else None

    async def set_render(render: dict) -> None:
        await db.clips.update_one({"_id": cid}, {"$set": {field: render}}, array_filters=filters)

    await set_render({"status": "rendering", "url": None, "rendered_at": None})
    await update_job(job_id, step="rendering", progress=10)
    try:
        work = asset_dir(str(asset["_id"]))
        out = work / "renders" / f"{clip_id}_{platform or 'main'}.mp4"
        m = asset["metadata"]
        await renderer.render(edl_doc, work / asset["filename"], out, m["width"], m["height"], m.get("fps") or 30)
        await update_job(job_id, step="publishing", progress=90)
        url = await storage.publish(out, str(clip["project_id"]))
        stamp = utcnow()
        await set_render({"status": "done", "url": f"{url}?v={int(stamp.timestamp())}", "rendered_at": stamp})
        await db.clips.update_one({"_id": cid}, {"$set": {"status": "exported"}})
        await workflow.advance(clip["project_id"], "scheduled")  # F7: exported
    except Exception:
        await set_render({"status": "failed", "url": None, "rendered_at": None})
        raise
