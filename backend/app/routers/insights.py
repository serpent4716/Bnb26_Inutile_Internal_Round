import json

from fastapi import APIRouter, Depends

from app.config import settings
from app.db import db
from app.errors import api_error
from app.models.common import utcnow
from app.models.generated_content import GeneratedContent
from app.services import insights, search
from app.services.auth import get_current_user

router = APIRouter(tags=["insights"])


@router.get("/insights/performance")
async def performance(user: dict = Depends(get_current_user)):
    return await insights.performance(user["_id"])


@router.get("/insights/production")
async def production(user: dict = Depends(get_current_user)):
    return await insights.production(user["_id"])


def data_fingerprint(perf: dict, prod: dict) -> dict:
    """Stored with the cards so the UI can tell when the numbers behind them have changed."""
    return {"posts": perf["totals"]["posts"], "views": perf["totals"]["views"], "stages": len(prod["time_per_stage"])}


@router.post("/insights/ai-summary", response_model=GeneratedContent)
async def ai_summary(user: dict = Depends(get_current_user)):
    """LLM insight cards from aggregated stats. Cached in generated_content (type "insights"); read the
    latest with GET /generated?type=insights instead of regenerating on page load."""
    perf, prod = await insights.performance(user["_id"]), await insights.production(user["_id"])
    if not perf["totals"]["posts"] and not prod["time_per_stage"]:
        raise api_error(400, "No data yet. Publish something or load sample analytics.", "NO_DATA")
    cards = await insights.ai_summary(user, perf, prod)
    doc = {"user_id": user["_id"], "project_id": None, "clip_id": None, "type": "insights", "platform": None,
           "variants": [{"text": c.body, "label": c.title, "selected": False, "score": None} for c in cards.cards],
           # compact separators so it compares equal to the frontend's JSON.stringify
           "prompt_context": json.dumps(data_fingerprint(perf, prod), separators=(",", ":")), "created_at": utcnow()}
    doc["_id"] = (await db.generated_content.insert_one(doc)).inserted_id
    return doc


def _dev_only():
    if not settings.ENABLE_DEV_ENDPOINTS:
        raise api_error(404, "Not found", "NOT_FOUND")


@router.post("/dev/seed-analytics", dependencies=[Depends(_dev_only)])
async def seed_analytics(user: dict = Depends(get_current_user)):
    """MOCK: realistic sample analytics for the current user (replaces earlier mock data)."""
    return {"inserted": await insights.seed_mock_analytics(user["_id"])}


@router.post("/dev/reindex-embeddings", dependencies=[Depends(_dev_only)])
async def reindex(user: dict = Depends(get_current_user)):
    """Build search embeddings for the user's assets that were transcribed before F1 search existed."""
    counts = {}
    async for a in db.assets.find({"user_id": user["_id"], "ai.status": "ready"}, {"_id": 1}):
        counts[str(a["_id"])] = await search.index_asset(a["_id"])
    return {"assets": len(counts), "chunks": sum(counts.values())}
