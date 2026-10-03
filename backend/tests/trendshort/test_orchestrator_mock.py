"""Mock-mode integration: no network, no keys. Stops before the slow FFmpeg render."""
import asyncio

from app.trendshort import orchestrator
from app.trendshort.agents import trend_agent
from app.trendshort.db import init_db


def test_review_mode_pauses_and_edits_mark_stale():
    async def go():
        init_db()
        t = await trend_agent.get_trends(region="ALL")
        assert len(t["ideas"]) == 12 and t["cluster_provider"] == "mock"
        idea = trend_agent.get_idea(t["ideas"][0]["id"])
        run = orchestrator.create_run(idea, "review", None)
        await orchestrator.drive(run["id"])
        r = orchestrator.get_run(run["id"])
        assert r["state"] == "scripting" and r["awaiting_approval"] and r["next_stage"] == "audio"
        await orchestrator.drive(run["id"], "audio")
        r = orchestrator.get_run(run["id"])
        assert r["stages"]["audio"]["status"] == "done" and r["next_stage"] == "visuals"
        from app.trendshort.schemas import ScriptOutput
        s = ScriptOutput.model_validate(r["stages"]["script"]["output"])
        s.title = "Edited title"
        orchestrator.patch_script(run["id"], s)
        r = orchestrator.get_run(run["id"])
        assert r["stages"]["audio"]["status"] == "stale" and r["state"] == "scripting"
        assert r["stages"]["script"]["providers"][-1]["provider"] == "user-edit"
    asyncio.run(go())
