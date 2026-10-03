"""F1 step 3: Gemini Vision on keyframes -> asset tags, description, per-keyframe descriptions."""

import math

from bson import ObjectId
from pydantic import BaseModel

from app.db import db
from app.services import llm
from app.services.media import KEYFRAME_EVERY_S
from app.services.storage import asset_dir

# ponytail: describes at most 24 evenly spaced frames (~2 calls); long footage gets coarser "nearest
# keyframe" visuals. Describe more frames, or only the ones near matched takes, if that matters.
MAX_FRAMES = 24
BATCH = 12


class FrameDescription(BaseModel):
    i: int
    description: str


class FrameBatch(BaseModel):
    frames: list[FrameDescription]
    tags: list[str]
    description: str


PROMPT = (
    "These are {n} keyframes from one creator video, in order, numbered 0 to {last}. "
    "For each frame give a short visual description (who or what is on screen, setting, notable objects, "
    "under 15 words). Then give 5-10 short lowercase tags for the footage overall and a one-sentence description."
)


async def tag_asset(asset_id: str) -> None:
    frames = sorted((asset_dir(asset_id) / "keyframes").glob("kf_*.jpg"))
    if not frames:
        return
    picked = frames[:: max(1, math.ceil(len(frames) / MAX_FRAMES))]

    keyframes, tags, descriptions = [], [], []
    for b in range(0, len(picked), BATCH):
        batch = picked[b:b + BATCH]
        res = await llm.generate_json(PROMPT.format(n=len(batch), last=len(batch) - 1), FrameBatch, images=batch)
        by_i = {f.i: f.description for f in res.frames}
        keyframes += [
            {"t": (int(p.stem.split("_")[1]) - 1) * KEYFRAME_EVERY_S, "description": by_i.get(i, "")}
            for i, p in enumerate(batch)
        ]
        tags += res.tags
        descriptions.append(res.description)

    await db.assets.update_one({"_id": ObjectId(asset_id)}, {"$set": {
        "ai.tags": list(dict.fromkeys(t.strip().lower() for t in tags if t.strip()))[:15],
        "ai.description": " ".join(descriptions),
        "ai.keyframes": keyframes,
    }})
