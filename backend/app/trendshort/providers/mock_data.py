"""Canned data for MOCK_MODE, driven by demo_assets/trends_seed.json."""
from __future__ import annotations

import json
from functools import lru_cache

from ..config import settings


@lru_cache
def seed() -> list[dict]:
    p = settings.demo_assets / "trends_seed.json"
    if not p.exists():
        raise FileNotFoundError(f"Mock seed not found at {p}. Run `python scripts/make_demo_assets.py`.")
    return json.loads(p.read_text(encoding="utf-8"))


def seed_by_id() -> dict[str, dict]:
    return {t["id"]: t for t in seed()}


def _seed_for_idea(idea: dict) -> dict | None:
    by_id = seed_by_id()
    for tid in idea.get("trend_ids", []) + [idea.get("id", "")]:
        if tid in by_id:
            return by_id[tid]
    return None


def _generic_script(idea: dict) -> dict:
    t = idea.get("title", "this trend")
    return {
        "title": t[:90], "hook": f"Everyone is talking about this.",
        "scenes": [[f"{t} is blowing up right now.", "crowd city"],
                   [f"Here's the short version of why.", "people phone scrolling"],
                   [idea.get("why_trending", "It hit a nerve online."), "social media"],
                   ["And it's probably not going away soon.", "timelapse city night"]],
        "on_screen": ["Trending", "Why?", "The reason", "Here to stay", "Follow"],
        "cta": "Follow for daily trend breakdowns.", "hashtags": ["#trending", "#shorts"],
        "description": f"A quick breakdown of {t}.",
    }


def llm_response(task: str, ctx: dict) -> dict:
    if task == "trends.cluster":
        ideas = []
        by_id = seed_by_id()
        for item in ctx.get("items", []):
            s = by_id.get(item["id"])
            i = (s or {}).get("idea", {})
            ideas.append({
                "trend_ids": [item["id"]], "title": item["title"],
                "hook_angle": i.get("hook_angle", f"The surprising story behind {item['title']}"),
                "why_trending": i.get("why_trending", f"Rising fast on {item['source']}."),
                "target_platform": i.get("target_platform", "youtube_shorts"),
                "estimated_length_sec": i.get("estimated_length_sec", 30),
                "category": item.get("category", "general"),
            })
        return {"ideas": ideas}

    idea = ctx.get("idea", {})
    script = (_seed_for_idea(idea) or {}).get("script") or _generic_script(idea)

    if task == "script.hook":
        return {"title": script["title"], "hook": script["hook"]}
    if task == "script.scenes":
        return {"scenes": [{"narration": n, "visual_query": q} for n, q in script["scenes"]]}
    if task == "script.packaging":
        n = int(ctx.get("n_scenes", len(script["on_screen"])))
        texts = (script["on_screen"] + ["Follow for more"] * n)[:n]
        return {"on_screen_text": texts, "cta": script["cta"], "hashtags": script["hashtags"],
                "description": script["description"]}
    if task == "visuals.rank":
        return {"picks": [{"scene_id": s["scene_id"], "best": 0} for s in ctx.get("scenes", [])]}
    raise ValueError(f"mock has no canned response for task {task!r}")
