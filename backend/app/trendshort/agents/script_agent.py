"""ScriptAgent: three small LLM calls (hook -> scenes -> packaging) instead of one giant prompt,
because small free models degrade on long multi-part instructions."""
from __future__ import annotations

import json

from pydantic import ValidationError

from ..providers.llm import generate_json
from ..schemas import (HOOK_MAX_WORDS, SCRIPT_MAX_SEC, SCRIPT_MIN_SEC, HookPart, PackagingPart, Scene,
                       ScenesPart, ScriptInput, ScriptOutput)

WORDS_PER_SEC = 2.5
SCENE_PAD = 0.3


def estimate_seconds(text: str) -> float:
    return round(len(text.split()) / WORDS_PER_SEC + SCENE_PAD, 2)


def _system(voice_profile: str | None) -> str:
    s = ("You write scripts for vertical short-form videos (YouTube Shorts, TikTok, Reels). "
         "Plain spoken English, short sentences, no emojis, no stage directions, no claims you can't support.")
    if voice_profile:
        s += f"\nMatch this creator's voice and style:\n{voice_profile[:800]}"
    return s


def _idea_brief(inp: ScriptInput) -> str:
    i = inp.idea
    return (f"Topic: {i.title}\nAngle: {i.hook_angle}\nWhy it's trending: {i.why_trending}\n"
            f"Platform: {i.target_platform}")


def fit_durations(scenes: list[Scene]) -> list[Scene]:
    """Durations are estimates (real audio drives timing later). Keep the estimate inside the
    20-45s window so validation reflects the target, scaling proportionally if needed."""
    total = sum(s.duration_sec for s in scenes)
    target = min(max(total, SCRIPT_MIN_SEC), SCRIPT_MAX_SEC)
    if abs(total - target) < 1e-6:
        return scenes
    k = target / total
    return [s.model_copy(update={"duration_sec": round(min(s.duration_sec * k, 15), 2)}) for s in scenes]


def assemble(hook: HookPart, body: ScenesPart, pack: PackagingPart) -> ScriptOutput:
    raw = [(hook.hook, body.scenes[0].visual_query)]
    raw += [(s.narration, s.visual_query) for s in body.scenes]
    raw += [(pack.cta, body.scenes[-1].visual_query)]
    texts = list(pack.on_screen_text) + [""] * len(raw)
    scenes = [Scene(id=f"s{i + 1}", narration=n.strip(), visual_query=q.strip()[:80],
                    on_screen_text=texts[i].strip()[:60], duration_sec=estimate_seconds(n))
              for i, (n, q) in enumerate(raw)]
    scenes = fit_durations(scenes)
    return ScriptOutput(title=hook.title, hook=hook.hook, scenes=scenes, cta=pack.cta,
                        hashtags=pack.hashtags, description=pack.description)


async def run(inp: ScriptInput) -> tuple[ScriptOutput, list[str]]:
    system = _system(inp.voice_profile)
    brief = _idea_brief(inp)
    ctx = {"idea": inp.idea.model_dump()}
    providers: list[str] = []

    hook, p = await generate_json(
        "script.hook", system,
        f"{brief}\n\nWrite a video title (max 70 chars) and a spoken hook of at most {HOOK_MAX_WORDS} words "
        f"that creates curiosity in the first 3 seconds.\nJSON keys: title, hook.",
        HookPart, ctx)
    providers.append(p)

    scenes_prompt = (f"{brief}\nHook (already written, do not repeat it): {hook.hook}\n\n"
                     "Write 4 to 6 narration beats that pay off the hook. Each beat is one or two short sentences. "
                     "Aim for 50 to 90 words in total. For each beat give a 2-5 word stock-footage search query "
                     "describing something filmable (no people's names, no logos).\n"
                     'JSON: {"scenes":[{"narration":"...","visual_query":"..."}]}')
    body, p = await generate_json("script.scenes", system, scenes_prompt, ScenesPart, ctx)
    providers.append(p)
    words = len(hook.hook.split()) + sum(len(s.narration.split()) for s in body.scenes)
    if words < 40:   # too short to reach ~20s: one targeted retry
        body, p = await generate_json(
            "script.scenes", system,
            scenes_prompt + f"\nYour last draft was only {words} words. Write 60 to 90 words in total.",
            ScenesPart, ctx, use_cache=False)
        providers.append(p)

    n = len(body.scenes) + 2
    pack, p = await generate_json(
        "script.packaging", system,
        f"{brief}\nScenes in order:\n" + json.dumps([hook.hook] + [s.narration for s in body.scenes] + ["(call to action)"]) +
        f"\n\nReturn exactly {n} on_screen_text captions (max 5 words each, one per scene, in order), "
        "a short spoken call to action (cta, under 12 words), 3-6 hashtags, and a 1-2 sentence description.\n"
        "JSON keys: on_screen_text, cta, hashtags, description.",
        PackagingPart, {**ctx, "n_scenes": n})
    providers.append(p)

    try:
        return assemble(hook, body, pack), providers
    except ValidationError as e:
        raise ValueError(f"Assembled script failed validation: {e}") from e
