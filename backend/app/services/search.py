"""F1 semantic search: ~30s transcript chunks + visual descriptions -> Gemini embeddings -> `embeddings`.

Atlas Vector Search index (Atlas UI -> Database -> Atlas Search -> Create Search Index ->
JSON Editor -> "Atlas Vector Search", collection `embeddings`, index name `embeddings_vector`):

    {
      "fields": [
        {"type": "vector", "path": "vector", "numDimensions": 768, "similarity": "cosine"},
        {"type": "filter", "path": "user_id"}
      ]
    }

Until that index exists and is queryable, search falls back to the Mongo text index on embeddings.text.
($vectorSearch against a missing index returns [] instead of failing, so we check the index first.)
"""

import logging
import time

from bson import ObjectId
from rapidfuzz import fuzz

from app.db import db
from app.models.common import utcnow
from app.services import llm
from app.services.alignment import normalize
from app.services.transcription import sentences

log = logging.getLogger("uvicorn.error")

INDEX_NAME = "embeddings_vector"
CHUNK_S = 30
INDEX_CHECK_TTL_S = 60
SNIPPET_MATCH = 50  # min token_set_ratio for a sentence to count as the matching line

_index_cache: tuple[float, bool] = (0.0, False)


def chunk_transcript(words: list[dict]) -> list[dict]:
    """~CHUNK_S windows that end on sentence boundaries."""
    chunks, cur = [], []
    for s in sentences(words):
        cur.append(s)
        if cur[-1]["end"] - cur[0]["start"] >= CHUNK_S:
            chunks.append(cur)
            cur = []
    if cur:
        chunks.append(cur)
    return [{"text": " ".join(s["text"] for s in c), "start": c[0]["start"], "end": c[-1]["end"]} for c in chunks]


async def index_asset(asset_id: ObjectId) -> int:
    """(Re)build an asset's embeddings. Returns how many chunks were indexed."""
    asset = await db.assets.find_one({"_id": asset_id})
    transcript = await db.transcripts.find_one({"asset_id": asset_id}, {"segments.words": 1})
    base = {"user_id": asset["user_id"], "asset_id": asset_id}
    docs = []
    if transcript:
        words = [w for s in transcript["segments"] for w in s["words"]]
        docs += [{**base, "kind": "transcript_chunk", **c} for c in chunk_transcript(words)]
    ai = asset.get("ai", {})
    if ai.get("description"):
        text = ai["description"] + (" Tags: " + ", ".join(ai["tags"]) if ai.get("tags") else "")
        docs.append({**base, "kind": "visual_description", "text": text, "start": None, "end": None})
    if not docs:
        return 0
    vectors = await llm.embed([d["text"] for d in docs], task="RETRIEVAL_DOCUMENT")
    for d, v in zip(docs, vectors):
        d["vector"], d["created_at"] = v, utcnow()
    await db.embeddings.delete_many({"asset_id": asset_id})
    await db.embeddings.insert_many(docs)
    return len(docs)


async def vector_index_ready() -> bool:
    """Is the Atlas Vector Search index present and queryable? Cached for a minute."""
    global _index_cache
    checked, ready = _index_cache
    if time.monotonic() - checked < INDEX_CHECK_TTL_S:
        return ready
    try:
        found = await db.embeddings.list_search_indexes(INDEX_NAME).to_list(1)
        ready = bool(found) and bool(found[0].get("queryable"))
    except Exception:  # not Atlas, or no permission
        ready = False
    _index_cache = (time.monotonic(), ready)
    return ready


def best_sentence(query: str, words: list[dict], start: float, end: float) -> dict | None:
    """The sentence inside [start, end] that best matches the query words, so results jump to the line itself."""
    q = normalize(query)
    inside = [s for s in sentences([w for w in words if w["start"] >= start - 0.01 and w["end"] <= end + 0.01])]
    scored = [(fuzz.token_set_ratio(q, normalize(s["text"])), s) for s in inside]
    best = max(scored, key=lambda x: x[0], default=None)
    return best[1] if best and best[0] >= SNIPPET_MATCH else None


async def search(user_id: ObjectId, query: str, limit: int = 8) -> list[dict]:
    if await vector_index_ready():
        qvec = (await llm.embed([query], task="RETRIEVAL_QUERY"))[0]
        pipeline = [
            {"$vectorSearch": {"index": INDEX_NAME, "path": "vector", "queryVector": qvec,
                               "numCandidates": limit * 20, "limit": limit, "filter": {"user_id": user_id}}},
            {"$project": {"vector": 0, "score": {"$meta": "vectorSearchScore"}}},
        ]
        match = "semantic"
    else:
        pipeline = [
            {"$match": {"$text": {"$search": query}, "user_id": user_id}},
            {"$project": {"vector": 0, "score": {"$meta": "textScore"}}},
            {"$sort": {"score": -1}},
            {"$limit": limit},
        ]
        match = "keyword"
    hits = await db.embeddings.aggregate(pipeline).to_list(limit)
    if not hits:
        return []

    asset_ids = list({h["asset_id"] for h in hits})
    assets = {a["_id"]: a async for a in db.assets.find({"_id": {"$in": asset_ids}, "user_id": user_id})}
    words_by_asset = {t["asset_id"]: [w for s in t["segments"] for w in s["words"]]
                      async for t in db.transcripts.find({"asset_id": {"$in": asset_ids}}, {"asset_id": 1, "segments.words": 1})}
    results = []
    for h in hits:
        if h["asset_id"] not in assets:
            continue
        start, end, snippet = h.get("start"), h.get("end"), h["text"]
        if h["kind"] == "transcript_chunk":
            line = best_sentence(query, words_by_asset.get(h["asset_id"], []), start, end)
            if line:
                start, end, snippet = line["start"], line["end"], line["text"]
        if len(snippet) > 220:
            snippet = snippet[:217].rsplit(" ", 1)[0] + "..."
        results.append({"asset": assets[h["asset_id"]], "start": start, "end": end, "snippet": snippet,
                        "score": round(h["score"], 4), "kind": h["kind"], "match": match})
    return results
