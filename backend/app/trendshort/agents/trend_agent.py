"""TrendAgent: fetch from pluggable providers -> LLM clusters duplicates and writes Short Ideas.
Cached for TREND_CACHE_MINUTES (default 30)."""
from __future__ import annotations

import json
import logging
import time

from ..cache import DiskCache, stable_hash
from ..config import settings
from ..db import SessionLocal, TrendIdeaRow
from ..logging_setup import log
from ..providers import trends as trend_providers
from ..providers.llm import LLMError, generate_json
from ..schemas import ClusterOutput, ShortIdea, TrendItem
from ..tracking import StageTracker, current_tracker

logger = logging.getLogger("t2s.trends")
_cache = DiskCache("trends")
BATCH = 20   # small batches: weak free models lose track of long lists


def _fallback_ideas(items: list[TrendItem]) -> list[ShortIdea]:
    return [ShortIdea(id=i.id, title=i.title, hook_angle=f"What's behind \"{i.title[:60]}\"",
                      why_trending=f"High momentum on {i.source.replace('_', ' ')}.", category=i.category,
                      region=i.region, momentum_score=i.momentum_score, sources=[i.source],
                      sample_urls=i.sample_urls, trend_ids=[i.id], estimated_length_sec=30) for i in items]


async def _cluster(items: list[TrendItem]) -> tuple[list[ShortIdea], str]:
    by_id = {i.id: i for i in items}
    ideas: list[ShortIdea] = []
    provider = "none"
    for k in range(0, len(items), BATCH):
        batch = items[k:k + BATCH]
        listing = [{"id": i.id, "title": i.title, "source": i.source} for i in batch]
        try:
            out, provider = await generate_json(
                "trends.cluster",
                "You turn trending topics into ideas for 20-45 second vertical videos. Skip anything about "
                "tragedies, specific private people, explicit content, or that can't be shown with stock footage.",
                "Merge items that are about the same story. For each idea give: trend_ids (ids merged), title, "
                "hook_angle (one punchy angle), why_trending (one sentence), target_platform "
                "(youtube_shorts|tiktok|instagram_reels), estimated_length_sec (20-45), category.\n"
                f"Items:\n{json.dumps(listing, ensure_ascii=False)}\n"
                'JSON: {"ideas":[...]}',
                ClusterOutput, {"items": [i.model_dump() for i in batch]})
        except LLMError as e:
            log(logger, "clustering failed, using raw trends", logging.WARNING, error=str(e)[:200])
            ideas += _fallback_ideas(batch)
            provider = "heuristic"
            continue
        for c in out.ideas:
            members = [by_id[t] for t in c.trend_ids if t in by_id]
            if not members:
                continue
            lead = max(members, key=lambda m: m.momentum_score)
            boost = min(10, 3 * (len({m.source for m in members}) - 1))   # cross-source agreement
            ideas.append(ShortIdea(
                id=lead.id, title=c.title, hook_angle=c.hook_angle, why_trending=c.why_trending,
                target_platform=c.target_platform, estimated_length_sec=max(20, min(45, c.estimated_length_sec)),
                category=c.category if c.category != "general" else lead.category, region=lead.region,
                momentum_score=min(100, lead.momentum_score + boost),
                sources=sorted({m.source for m in members}),
                sample_urls=[u for m in members for u in m.sample_urls][:4], trend_ids=[m.id for m in members]))
    return ideas, provider


async def get_trends(region: str = "US", category: str | None = None, refresh: bool = False) -> dict:
    current_tracker.set(StageTracker())
    key = stable_hash({"region": region, "category": category, "mock": settings.mock_mode})
    ttl = settings.trend_cache_minutes * 60
    if not refresh and (hit := _cache.get(key, ttl_seconds=ttl)):
        return {**hit, "cached": True}
    items, status = await trend_providers.fetch_all(region, category)
    if not items:
        return {"ideas": [], "providers": status, "cluster_provider": None, "cached": False,
                "fetched_at": time.time(),
                "message": "No trend source returned data. Set YOUTUBE_API_KEY, check network, or set MOCK_MODE=true."}
    ideas, cluster_provider = await _cluster(items)
    ideas.sort(key=lambda i: -i.momentum_score)
    with SessionLocal() as db:
        for i in ideas:
            db.merge(TrendIdeaRow(id=i.id, data=i.model_dump()))
        db.commit()
    result = {"ideas": [i.model_dump() for i in ideas], "providers": status,
              "cluster_provider": cluster_provider, "fetched_at": time.time()}
    _cache.set(key, result)
    return {**result, "cached": False}


def get_idea(trend_id: str) -> ShortIdea | None:
    with SessionLocal() as db:
        row = db.get(TrendIdeaRow, trend_id)
        return ShortIdea.model_validate(row.data) if row else None
