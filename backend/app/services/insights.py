"""F8: performance insights (analytics, mock-seeded) + production insights (real stage_history + jobs)."""

import json
import random
from datetime import timedelta

from bson import ObjectId
from pydantic import BaseModel

from app.db import db
from app.models.common import utcnow
from app.services import llm
from app.services.workflow import STAGES

# Time-saved model. Calibration knobs, shown to the creator alongside the number:
MANUAL_MIN_PER_FOOTAGE_MIN = 3   # scrubbing + logging raw footage by hand
MANUAL_MIN_PER_CLIP = 20         # cutting, captioning and reframing one short by hand

# ---------- MOCK: analytics generator (no real platform APIs connected) ----------

MOCK_PLATFORMS = {  # MOCK: median views and share of posts per platform
    "shorts": (8200, 0.3), "reels": (6400, 0.25), "tiktok": (11500, 0.2), "linkedin": (1900, 0.12), "x": (1400, 0.08), "youtube": (3100, 0.05),
}
MOCK_HOOKS = {  # MOCK: 3-second retention per hook type (question hooks deliberately strongest)
    "question": 0.71, "contrarian": 0.66, "bold_claim": 0.62, "story": 0.58, "statistic": 0.51,
}
MOCK_TITLES = [
    "The 3 money mistakes I made at 22", "Why your budget keeps failing", "I tried saving 50% for a month",
    "Stop buying index funds like this", "The rent rule nobody tells you", "My worst stock tip, explained",
    "How I automate 20% of my salary", "Credit cards are not the enemy", "What I would do with my first salary",
    "The coffee myth, debunked", "Emergency funds: how much is enough", "One habit that doubled my savings",
]


def mock_post(rng: random.Random, platform: str, hook_type: str, posted_at, title: str) -> dict:
    """MOCK: one post's metrics. Weekday evenings and strong hooks do better, with lognormal noise."""
    median, _ = MOCK_PLATFORMS[platform]
    retention = min(0.95, max(0.2, rng.gauss(MOCK_HOOKS[hook_type], 0.05)))
    timing = (1.25 if posted_at.weekday() in (1, 3) else 1.0) * (1.3 if 13 <= posted_at.hour <= 16 else 0.9)  # UTC 13-16 = IST evening
    views = int(median * timing * (retention / 0.6) ** 2 * rng.lognormvariate(0, 0.55))
    return {
        "platform": platform, "hook_type": hook_type, "title": title, "posted_at": posted_at,
        "metrics": {
            "views": views,
            "likes": int(views * rng.uniform(0.03, 0.06)),
            "comments": int(views * rng.uniform(0.002, 0.006)),
            "shares": int(views * rng.uniform(0.004, 0.012) * (1.5 if hook_type == "contrarian" else 1)),
            "watch_time_avg": round(rng.uniform(14, 32) * retention / 0.6, 1),
            "retention_3s": round(retention, 3),
        },
        "snapshot_at": utcnow(), "mock": True,
    }


async def seed_mock_analytics(user_id: ObjectId, posts: int = 64, days: int = 90) -> int:
    """MOCK: replace this user's mock analytics with `posts` posts over the last `days` days."""
    rng = random.Random(str(user_id))  # same user -> same data
    platforms, weights = zip(*((p, w) for p, (_, w) in MOCK_PLATFORMS.items()))
    now = utcnow().replace(minute=0, second=0, microsecond=0)
    docs = []
    for _ in range(posts):  # not linked to real projects: unpublished work must never show up as a "top post"
        posted = now - timedelta(days=rng.uniform(1, days), hours=rng.randint(0, 23))
        doc = mock_post(rng, rng.choices(platforms, weights)[0], rng.choice(list(MOCK_HOOKS)), posted, rng.choice(MOCK_TITLES))
        docs.append({"user_id": user_id, "project_id": None, "clip_id": None, **doc})
    await db.analytics.delete_many({"user_id": user_id, "mock": True, "project_id": None})  # keep mock-publish posts
    await db.analytics.insert_many(docs)
    return len(docs)


# ---------- performance (analytics) ----------

ENGAGEMENT = {"$divide": [{"$add": ["$metrics.likes", "$metrics.comments", "$metrics.shares"]}, {"$max": ["$metrics.views", 1]}]}


async def performance(user_id: ObjectId) -> dict:
    def per(key):
        return [{"$group": {"_id": key, "posts": {"$sum": 1}, "avg_views": {"$avg": "$metrics.views"},
                            "avg_retention_3s": {"$avg": "$metrics.retention_3s"}, "avg_engagement": {"$avg": ENGAGEMENT}}}]

    [facets] = await db.analytics.aggregate([
        {"$match": {"user_id": user_id}},
        {"$facet": {
            "totals": [{"$group": {"_id": None, "posts": {"$sum": 1}, "views": {"$sum": "$metrics.views"},
                                   "avg_retention_3s": {"$avg": "$metrics.retention_3s"}, "avg_engagement": {"$avg": ENGAGEMENT},
                                   "mock": {"$max": {"$ifNull": ["$mock", False]}}}}],
            "by_hook": per("$hook_type") + [{"$sort": {"avg_retention_3s": -1}}],
            "by_platform": per("$platform") + [{"$sort": {"avg_views": -1}}],
            "by_weekday": per({"$dayOfWeek": "$posted_at"}) + [{"$sort": {"_id": 1}}],   # 1 = Sunday
            "by_hour": per({"$hour": "$posted_at"}) + [{"$sort": {"_id": 1}}],            # UTC
            "weekly": [{"$group": {"_id": {"$dateTrunc": {"date": "$posted_at", "unit": "week"}},
                                   "posts": {"$sum": 1}, "views": {"$sum": "$metrics.views"}}}, {"$sort": {"_id": 1}}],
            "top_posts": [{"$sort": {"metrics.views": -1}}, {"$limit": 5},
                          {"$project": {"_id": 0, "title": 1, "platform": 1, "hook_type": 1, "posted_at": 1,
                                        "views": "$metrics.views", "retention_3s": "$metrics.retention_3s"}}],
        }},
    ]).to_list(1)

    def rows(items, key="key"):
        return [{key: r["_id"], **{k: (round(v, 4) if isinstance(v, float) else v) for k, v in r.items() if k != "_id"}} for r in items]

    totals = facets["totals"][0] if facets["totals"] else {"posts": 0, "views": 0, "avg_retention_3s": 0, "avg_engagement": 0, "mock": False}
    totals.pop("_id", None)
    return {
        "totals": totals,
        "by_hook": rows(facets["by_hook"], "hook_type"),
        "by_platform": rows(facets["by_platform"], "platform"),
        "by_weekday": rows(facets["by_weekday"], "weekday"),
        "by_hour": rows(facets["by_hour"], "hour_utc"),
        "weekly": rows(facets["weekly"], "week"),
        "top_posts": facets["top_posts"],
    }


# ---------- production (real stage_history + jobs) ----------

async def production(user_id: ObjectId) -> dict:
    stage_rows = await db.projects.aggregate([
        {"$match": {"user_id": user_id}},
        {"$unwind": "$stage_history"},
        {"$setWindowFields": {"partitionBy": "$_id", "sortBy": {"stage_history.at": 1},
                              "output": {"next_at": {"$shift": {"output": "$stage_history.at", "by": 1}}}}},
        {"$match": {"next_at": {"$ne": None}}},   # completed stages only
        {"$group": {"_id": "$stage_history.stage", "avg_hours": {"$avg": {"$divide": [{"$subtract": ["$next_at", "$stage_history.at"]}, 3_600_000]}},
                    "samples": {"$sum": 1}}},
    ]).to_list(20)
    stage_time = {r["_id"]: r for r in stage_rows}
    time_per_stage = [{"stage": s, "avg_hours": round(stage_time[s]["avg_hours"], 3), "samples": stage_time[s]["samples"]}
                      for s in STAGES if s in stage_time]

    counts = {r["_id"]: r["n"] for r in await db.projects.aggregate([
        {"$match": {"user_id": user_id}}, {"$group": {"_id": "$stage", "n": {"$sum": 1}}}]).to_list(20)}
    published_weekly = await db.projects.aggregate([
        {"$match": {"user_id": user_id, "published_at": {"$ne": None}}},
        {"$group": {"_id": {"$dateTrunc": {"date": "$published_at", "unit": "week"}}, "published": {"$sum": 1}}},
        {"$sort": {"_id": 1}}, {"$project": {"_id": 0, "week": "$_id", "published": 1}},
    ]).to_list(200)

    jobs = await db.jobs.aggregate([
        {"$match": {"user_id": user_id, "finished_at": {"$ne": None}}},
        {"$group": {"_id": "$type", "runs": {"$sum": 1}, "failed": {"$sum": {"$cond": [{"$eq": ["$status", "failed"]}, 1, 0]}},
                    "avg_seconds": {"$avg": {"$divide": [{"$subtract": ["$finished_at", "$created_at"]}, 1000]}},
                    "total_seconds": {"$sum": {"$divide": [{"$subtract": ["$finished_at", "$created_at"]}, 1000]}}}},
        {"$sort": {"runs": -1}},
    ]).to_list(20)

    project_ids = [p["_id"] for p in await db.projects.find({"user_id": user_id}, {"_id": 1}).to_list(1000)]
    [footage] = await db.assets.aggregate([
        {"$match": {"user_id": user_id, "type": "video"}},
        {"$group": {"_id": None, "minutes": {"$sum": {"$divide": [{"$ifNull": ["$metadata.duration", 0]}, 60]}}, "files": {"$sum": 1}}},
    ]).to_list(1) or [{"minutes": 0, "files": 0}]
    [clips] = await db.clips.aggregate([
        {"$match": {"project_id": {"$in": project_ids}, "kind": "short", "status": {"$in": ["approved", "exported"]}}},
        {"$group": {"_id": None, "n": {"$sum": 1}, "minutes": {"$sum": {"$divide": [{"$reduce": {
            "input": "$edl.segments", "initialValue": 0, "in": {"$add": ["$$value", {"$subtract": ["$$this.end", "$$this.start"]}]}}}, 60]}}}},
    ]).to_list(1) or [{"n": 0, "minutes": 0}]
    ai_minutes = sum(j["total_seconds"] for j in jobs) / 60
    manual = footage["minutes"] * MANUAL_MIN_PER_FOOTAGE_MIN + clips["n"] * MANUAL_MIN_PER_CLIP

    bottleneck = max(time_per_stage, key=lambda r: r["avg_hours"], default=None)
    return {
        "projects_by_stage": [{"stage": s, "projects": counts.get(s, 0)} for s in STAGES],
        "time_per_stage": time_per_stage,
        "bottleneck": bottleneck["stage"] if bottleneck else None,
        "published_weekly": published_weekly,
        "jobs": [{"type": j["_id"], "runs": j["runs"], "failed": j["failed"], "avg_seconds": round(j["avg_seconds"], 1)} for j in jobs],
        "time_saved": {
            "raw_footage_minutes": round(footage["minutes"], 2),
            "footage_files": footage["files"],
            "final_clip_minutes": round(clips["minutes"], 2),
            "clips_ready": clips["n"],
            "ai_processing_minutes": round(ai_minutes, 2),
            "manual_estimate_minutes": round(manual, 1),
            "minutes_saved": round(max(0.0, manual - ai_minutes), 1),
            "assumptions": {"manual_min_per_footage_min": MANUAL_MIN_PER_FOOTAGE_MIN, "manual_min_per_clip": MANUAL_MIN_PER_CLIP},
        },
    }


# ---------- AI insight cards ----------

class Card(BaseModel):
    title: str
    body: str


class Cards(BaseModel):
    cards: list[Card]


def compact(perf: dict, prod: dict) -> dict:
    """Aggregates only (no raw rows) for the LLM, trimmed to what an insight needs."""
    keep = ("posts", "avg_views", "avg_retention_3s", "avg_engagement")
    return {
        "performance_is_sample_data": bool(perf["totals"].get("mock")),
        "performance_totals": perf["totals"],
        "by_hook_type": [{"hook_type": r["hook_type"], **{k: r[k] for k in keep}} for r in perf["by_hook"]],
        "by_platform": [{"platform": r["platform"], **{k: r[k] for k in keep}} for r in perf["by_platform"]],
        "by_weekday_1_is_sunday": [{"weekday": r["weekday"], "avg_views": round(r["avg_views"])} for r in perf["by_weekday"]],
        "by_hour_utc": [{"hour": r["hour_utc"], "avg_views": round(r["avg_views"]), "posts": r["posts"]} for r in perf["by_hour"]],
        "production_time_per_stage_hours": prod["time_per_stage"],
        "production_bottleneck": prod["bottleneck"],
        "time_saved": prod["time_saved"],
    }


async def ai_summary(user: dict, perf: dict, prod: dict) -> Cards:
    stats = json.dumps(compact(perf, prod), default=str)
    prompt = (
        f"You are a growth analyst for a {user.get('niche') or 'general'} short-form creator.\n"
        "Below are aggregated stats from their content. Write 3-5 insight cards. Each card: a short title and a 1-2 "
        "sentence body that cites specific numbers from the data (ratios like '2.1x' or percentages), compares "
        "segments, and ends with one concrete action for their next posts. No generic advice; every claim must come "
        "from these numbers. Mention the production bottleneck if there is one.\n\n"
        f"Stats JSON:\n{stats}"
    )
    return await llm.generate_json(prompt, Cards, deep=True)
