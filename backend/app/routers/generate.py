from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field

from app.db import db, oid, owned, owned_clip
from app.errors import api_error
from app.models.common import utcnow
from app.models.generated_content import GeneratedContent, Platform
from app.services import llm
from app.services.auth import get_current_user
from app.services.edl import with_hook
from app.services.pipeline import clip_context, save_platform_copy
from app.services.scripts import ensure_tone_profile

router = APIRouter(tags=["generate"])


class ScriptIn(BaseModel):
    idea: str = Field(min_length=3)
    platform: Platform = "shorts"
    duration: int = Field(60, ge=15, le=600)   # seconds
    tone: str = ""                             # extra direction on top of the tone profile


class ScriptOut(BaseModel):
    id: str
    title: str
    content: str
    lines: list[llm.ScriptLineOut]


class HooksIn(BaseModel):
    project_id: str | None = None
    clip_id: str | None = None
    count: int = Field(5, ge=1, le=10)


class SupportingIn(BaseModel):
    clip_id: str
    platform: Platform


class IdeasIn(BaseModel):
    idea: str = Field(min_length=3)


class SelectIn(BaseModel):
    variant_index: int
    text: str | None = Field(None, min_length=1)  # the creator's edit of that variant


async def _insert(doc: dict) -> dict:
    doc["_id"] = (await db.generated_content.insert_one(doc)).inserted_id
    return doc


def _variants(items) -> list[dict]:
    return [{"text": t, "selected": i == 0, "score": s, "label": label} for i, (t, s, label) in enumerate(items)]


@router.post("/generate/script", response_model=ScriptOut)
async def generate_script(body: ScriptIn, user: dict = Depends(get_current_user)):
    tone = " ".join(filter(None, [await ensure_tone_profile(user), body.tone]))
    out = await llm.script(body.idea, body.platform, body.duration, user.get("niche", ""), tone)
    content = "\n".join(line.text for line in out.lines)
    doc = await _insert({"user_id": user["_id"], "project_id": None, "clip_id": None, "type": "script",
                         "platform": body.platform, "variants": _variants([(content, None, out.title)]),
                         "prompt_context": body.idea, "created_at": utcnow()})
    return {"id": str(doc["_id"]), "title": out.title, "content": content, "lines": out.lines}


@router.post("/generate/hooks", response_model=GeneratedContent)
async def generate_hooks(body: HooksIn, user: dict = Depends(get_current_user)):
    clip = await owned_clip(body.clip_id, user) if body.clip_id else None
    project = await owned("projects", body.project_id or str(clip["project_id"]), user) if (body.project_id or clip) else None
    if clip:
        text, _ = await clip_context(clip)
    elif project and project.get("script_id"):
        text = (await db.scripts.find_one({"_id": project["script_id"]}))["content"]
    else:
        raise api_error(400, "Give a clip_id, or a project_id with a script", "NO_TEXT")
    out = await llm.hooks(text, user.get("niche", ""), await ensure_tone_profile(user), body.count)
    ranked = sorted(out.hooks, key=lambda h: h.score, reverse=True)
    return await _insert({"user_id": user["_id"], "project_id": project["_id"] if project else None,
                          "clip_id": clip["_id"] if clip else None, "type": "hook", "platform": None,
                          "variants": [dict(v, selected=False) for v in _variants((h.text, h.score, h.type) for h in ranked)],
                          "prompt_context": text[:2000], "created_at": utcnow()})


@router.post("/generate/supporting", response_model=list[GeneratedContent])
async def generate_supporting(body: SupportingIn, user: dict = Depends(get_current_user)):
    clip = await owned_clip(body.clip_id, user)
    text, _ = await clip_context(clip)
    copyset = await llm.platform_copy(text, [body.platform], user.get("niche", ""), await ensure_tone_profile(user))
    return await save_platform_copy(clip, user["_id"], copyset)


@router.post("/generate/ideas", response_model=GeneratedContent)
async def generate_ideas(body: IdeasIn, user: dict = Depends(get_current_user)):
    out = await llm.ideas(body.idea, user.get("niche", ""), await ensure_tone_profile(user))
    return await _insert({"user_id": user["_id"], "project_id": None, "clip_id": None, "type": "ideas", "platform": None,
                          "variants": [dict(v, selected=False) for v in _variants((a.angle, None, a.title) for a in out.angles)],
                          "prompt_context": body.idea, "created_at": utcnow()})


@router.post("/generate/tone-profile")
async def refresh_tone_profile(user: dict = Depends(get_current_user)):
    """Rebuild users.tone_profile from the creator's latest scripts."""
    return {"tone_profile": await ensure_tone_profile(user, refresh=True)}


@router.get("/generated", response_model=list[GeneratedContent])
async def list_generated(clip_id: str | None = None, project_id: str | None = None, type: str | None = None,
                         platform: str | None = None, user: dict = Depends(get_current_user)):
    q: dict = {"user_id": user["_id"]}
    for key, value in (("clip_id", clip_id), ("project_id", project_id)):
        if value:
            q[key] = oid(value)
    for key, value in (("type", type), ("platform", platform)):
        if value:
            q[key] = value
    return await db.generated_content.find(q).sort("created_at", -1).to_list(200)


@router.patch("/generated/{generated_id}/select", response_model=GeneratedContent)
async def select_variant(generated_id: str, body: SelectIn, user: dict = Depends(get_current_user)):
    """Mark one variant selected (optionally with the creator's edited text). A selected hook becomes
    the clip's text overlay for the first 2s, on the main EDL and every platform variant."""
    doc = await owned("generated_content", generated_id, user)
    if not 0 <= body.variant_index < len(doc["variants"]):
        raise api_error(400, "No such variant", "INVALID_VARIANT")
    for i, v in enumerate(doc["variants"]):
        v["selected"] = i == body.variant_index
    if body.text:
        doc["variants"][body.variant_index]["text"] = body.text.strip()
    await db.generated_content.update_one({"_id": doc["_id"]}, {"$set": {"variants": doc["variants"]}})

    if doc["type"] == "hook" and doc.get("clip_id"):
        clip = await db.clips.find_one({"_id": doc["clip_id"]})
        text = doc["variants"][body.variant_index]["text"]
        main = with_hook(clip["edl"], text)

        def stale(render: dict) -> dict:  # existing MP4s no longer match the EDL
            return {**render, "status": "stale"} if render.get("url") else render

        variants = [dict(v, edl=with_hook(v["edl"], text), render=stale(v["render"])) for v in clip.get("variants", [])]
        await db.clips.update_one({"_id": clip["_id"]}, {
            "$set": {"edl": main, "variants": variants, "render": stale(clip["render"])},
            "$push": {"edl_versions": {"edl": main, "edited_by": "user", "at": utcnow()}},
        })
    return doc
