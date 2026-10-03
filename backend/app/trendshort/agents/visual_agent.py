"""VisualAgent: candidates per scene from the footage chain (sequential, rate-limited), ONE batched LLM
call to rank all scenes, download the winner, keep alternates for the visual picker."""
from __future__ import annotations

import json
import logging

from ..logging_setup import log
from ..providers import footage
from ..providers.llm import LLMError, generate_json
from ..ratelimit import ProviderUnavailable, RateLimited, TransientError
from ..schemas import AudioOutput, ClipCandidate, SceneVisual, ScriptOutput, VisualOutput, VisualRanking
from ..tracking import tracker

logger = logging.getLogger("t2s.visuals")
MAX_CANDIDATES = 4


async def _candidates(query: str) -> list[ClipCandidate]:
    t = tracker()
    out: list[ClipCandidate] = []
    for prov in footage.chain():
        ok, why = prov.configured()
        if not ok:
            t.fell_back(f"footage {prov.name}: skipped ({why})")
            continue
        try:
            got = await prov.search(query, n=MAX_CANDIDATES)
            t.add("api_requests", 1)
        except (ProviderUnavailable, TransientError, RateLimited) as e:
            t.fell_back(f"footage {prov.name}: {str(e)[:120]}")
            continue
        except Exception as e:  # noqa: BLE001 - never let one provider kill the run
            t.fell_back(f"footage {prov.name}: {type(e).__name__}")
            log(logger, "footage provider error", logging.WARNING, provider=prov.name, error=str(e)[:200])
            continue
        out.extend(got)
        if len([c for c in out if c.kind == "video"]) >= 2 or len(out) >= MAX_CANDIDATES:
            break
    return out[:MAX_CANDIDATES + 1]


async def rank(script: ScriptOutput, per_scene: dict[str, list[ClipCandidate]],
               durations: dict[str, float]) -> tuple[dict[str, int], str]:
    """One LLM call for all scenes. Falls back to a heuristic (prefer video long enough for the scene)."""
    def heuristic() -> dict[str, int]:
        picks = {}
        for sid, cands in per_scene.items():
            need = durations.get(sid, 3)
            scored = sorted(range(len(cands)), key=lambda i: (cands[i].kind != "video",
                                                               cands[i].duration_sec < need, i))
            picks[sid] = scored[0]
        return picks

    if all(len(c) <= 1 for c in per_scene.values()):
        return {sid: 0 for sid in per_scene}, "single-candidate"
    payload = [{"scene_id": s.id, "narration": s.narration[:140],
                "candidates": [f"{i}: {c.kind}, {c.description[:60]}, {c.duration_sec:.0f}s"
                               for i, c in enumerate(per_scene[s.id])]} for s in script.scenes]
    try:
        out, provider = await generate_json(
            "visuals.rank", "You pick stock footage that best matches each narration line.",
            "For each scene choose the best candidate index. Prefer video over image and clips at least as "
            "long as the line.\n" + json.dumps(payload) +
            '\nJSON: {"picks":[{"scene_id":"s1","best":0}]}',
            VisualRanking, {"scenes": [{"scene_id": s.id} for s in script.scenes]})
    except LLMError as e:
        tracker().fell_back(f"visual ranking LLM failed, used heuristic: {str(e)[:80]}")
        return heuristic(), "heuristic"
    picks = heuristic()
    for p in out.picks:
        sid, best = str(p.get("scene_id")), p.get("best")
        if sid in per_scene and isinstance(best, int) and 0 <= best < len(per_scene[sid]):
            picks[sid] = best
    return picks, provider


async def ensure_downloaded(sv: SceneVisual) -> SceneVisual:
    """Download the chosen clip; if it fails, walk the alternates instead of failing the scene."""
    order = [sv.chosen_index] + [i for i in range(len(sv.candidates)) if i != sv.chosen_index]
    last: Exception | None = None
    for i in order:
        c = sv.candidates[i]
        try:
            path = await footage.download(c)
            cands = list(sv.candidates)
            cands[i] = c.model_copy(update={"local_path": path})
            if i != sv.chosen_index:
                tracker().fell_back(f"{sv.scene_id}: chosen clip failed to download, used alternate {i}")
            return sv.model_copy(update={"candidates": cands, "chosen_index": i})
        except Exception as e:  # noqa: BLE001
            last = e
    raise RuntimeError(f"No downloadable footage for {sv.scene_id}: {last}")


async def run(script: ScriptOutput, audio: AudioOutput) -> VisualOutput:
    t = tracker()
    per_scene: dict[str, list[ClipCandidate]] = {}
    for s in script.scenes:
        cands = await _candidates(s.visual_query)
        if not cands:
            cands = await _candidates(" ".join(s.visual_query.split()[:2]) or "abstract background")
        if not cands:
            raise RuntimeError(f"No footage found for scene {s.id} ({s.visual_query!r}). "
                               "Set PEXELS_API_KEY or PIXABAY_API_KEY, or run scripts/make_demo_assets.py.")
        per_scene[s.id] = cands
        t.used(f"footage.{s.id}", cands[0].provider)
    durations = {a.scene_id: a.duration_sec for a in audio.scenes}
    picks, ranker = await rank(script, per_scene, durations)
    scenes = []
    for s in script.scenes:
        sv = SceneVisual(scene_id=s.id, chosen_index=picks.get(s.id, 0), candidates=per_scene[s.id])
        scenes.append(await ensure_downloaded(sv))
    return VisualOutput(scenes=scenes, ranking_provider=ranker)
