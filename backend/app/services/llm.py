"""Gemini wrapper (google-genai): structured JSON (text + images) and embeddings."""

import logging
from pathlib import Path
from typing import Literal, TypeVar

from google import genai
from google.genai import types
from pydantic import BaseModel, ValidationError

from app.config import settings

log = logging.getLogger("uvicorn.error")

T = TypeVar("T", bound=BaseModel)
EMBED_DIMS = 768
EMBED_BATCH = 100

_client: genai.Client | None = None


def client() -> genai.Client:
    global _client
    if _client is None:
        _client = genai.Client(
            api_key=settings.GEMINI_API_KEY,
            # retries 503 ("high demand") with backoff; 429 goes straight to the next model (daily quotas don't recover in seconds)
            http_options=types.HttpOptions(retry_options=types.HttpRetryOptions(attempts=4, http_status_codes=[500, 502, 503, 504])),
        )
    return _client


class LLMQuotaError(Exception):
    """Every configured model is rate-limited / out of quota."""


async def _generate(contents: list, config: types.GenerateContentConfig):
    """Primary model, then GEMINI_FALLBACK_MODELS on 429 (quotas are per model)."""
    models = [settings.GEMINI_TEXT_MODEL, *filter(None, (m.strip() for m in settings.GEMINI_FALLBACK_MODELS.split(",")))]
    for model in models:
        try:
            return await client().aio.models.generate_content(model=model, contents=contents, config=config)
        except genai.errors.ClientError as e:
            if e.code != 429:
                raise
            log.warning("Gemini %s is rate-limited/out of quota, trying the next model", model)
    raise LLMQuotaError(f"All Gemini models are out of quota: {', '.join(models)}")


async def generate_json(prompt: str, schema: type[T], images: list[Path] = ()) -> T:
    """Structured output validated against `schema`; retries once if the JSON doesn't parse."""
    contents = [types.Part.from_bytes(data=p.read_bytes(), mime_type="image/jpeg") for p in images] + [prompt]
    config = types.GenerateContentConfig(
        response_mime_type="application/json",
        response_schema=schema,
        automatic_function_calling=types.AutomaticFunctionCallingConfig(disable=True),
    )
    for attempt in (1, 2):
        resp = await _generate(contents, config)
        try:
            return schema.model_validate_json(resp.text or "")
        except ValidationError:
            if attempt == 2:
                raise
            log.warning("Gemini returned invalid JSON for %s, retrying once", schema.__name__)


async def embed(texts: list[str], task: str = "SEMANTIC_SIMILARITY") -> list[list[float]]:
    """Embeddings, batched. task: SEMANTIC_SIMILARITY | RETRIEVAL_DOCUMENT | RETRIEVAL_QUERY."""
    out: list[list[float]] = []
    for i in range(0, len(texts), EMBED_BATCH):
        resp = await client().aio.models.embed_content(
            model=settings.GEMINI_EMBED_MODEL,
            contents=texts[i:i + EMBED_BATCH],
            config=types.EmbedContentConfig(output_dimensionality=EMBED_DIMS, task_type=task),
        )
        out += [e.values for e in resp.embeddings]
    return out


# ---------- F2 prompts (every one takes the creator's tone profile) ----------

HOOK_TYPES = ["question", "bold_claim", "story", "statistic", "contrarian"]


class Hook(BaseModel):
    type: str
    text: str
    score: float


class Hooks(BaseModel):
    hooks: list[Hook]


class PlatformCopy(BaseModel):
    platform: str
    title: str
    caption: str
    hashtags: list[str]
    description: str
    thumbnail_text: str


class CopySet(BaseModel):
    platforms: list[PlatformCopy]


class ScriptLineOut(BaseModel):
    text: str
    section: Literal["hook", "intro", "body", "cta"]


class ScriptOut(BaseModel):
    title: str
    lines: list[ScriptLineOut]


class Angle(BaseModel):
    title: str
    angle: str


class Angles(BaseModel):
    angles: list[Angle]


class ToneSummary(BaseModel):
    tone: str


PLATFORM_VOICE = {
    "shorts": "YouTube Shorts: punchy, curiosity-driven title, 3-5 hashtags including #shorts",
    "reels": "Instagram Reels: casual and warm, a few emojis, line breaks, 5-10 hashtags",
    "tiktok": "TikTok: casual, trend-aware, very short caption, 3-5 hashtags",
    "youtube": "YouTube long-form: searchable title, keyword-rich description, 3-5 hashtags",
    "linkedin": "LinkedIn: professional and insight-led, no slang, a takeaway in the first line, 3 hashtags",
    "x": "X: under 240 characters, sharp and opinionated, 1-2 hashtags",
}


def _creator(niche: str, tone: str) -> str:
    return f"You write for a {niche or 'general'} creator." + (f"\nCreator tone: {tone}" if tone else "")


async def hooks(text: str, niche: str, tone: str, count: int = 5) -> Hooks:
    types_ = ", ".join(HOOK_TYPES[i % len(HOOK_TYPES)] for i in range(count))
    prompt = (
        f"You are a short-form content strategist. {_creator(niche, tone)}\n"
        f"Clip transcript: {text}\n"
        f"Write {count} hooks (under 12 words each), one per type in this order: {types_}. "
        "A hook is the on-screen line for the first 2 seconds. Score each 1-10 for scroll-stopping power."
    )
    return await generate_json(prompt, Hooks)


async def platform_copy(text: str, platforms: list[str], niche: str, tone: str) -> CopySet:
    voices = "\n".join(f"- {p}: {PLATFORM_VOICE[p]}" for p in platforms)
    prompt = (
        f"{_creator(niche, tone)}\nWrite posting copy for this clip on each platform below, adapted to that platform's style.\n"
        f"{voices}\n\nFor each: title, caption, hashtags (each starting with #), description (1-3 sentences), "
        f"thumbnail_text (2-5 words, big-text style).\n\nClip transcript: {text}"
    )
    return await generate_json(prompt, CopySet)


async def script(idea: str, platform: str, duration_s: int, niche: str, tone: str) -> ScriptOut:
    words = int(duration_s * 2.5)  # ~150 spoken words per minute
    prompt = (
        f"{_creator(niche, tone)}\nWrite a {duration_s}-second {platform} video script (about {words} spoken words) "
        f"about: {idea}\nOne sentence per line. Label each line hook, intro, body or cta: a 1-2 line hook that stops "
        "the scroll, a short intro, the body, and one cta line at the end. Write it to be spoken, not read."
    )
    return await generate_json(prompt, ScriptOut)


async def ideas(idea: str, niche: str, tone: str) -> Angles:
    prompt = (
        f"{_creator(niche, tone)}\nExpand this rough video idea into 3 distinct angles. For each, a one-sentence angle "
        f"and a clickable title.\nIdea: {idea}"
    )
    return await generate_json(prompt, Angles)


async def tone_summary(scripts: list[str]) -> ToneSummary:
    joined = "\n\n---\n\n".join(s[:4000] for s in scripts)
    prompt = (
        "Summarize this creator's voice in 2-3 sentences so another writer can imitate it: vocabulary, sentence "
        f"length, energy, humour, how they address the viewer, recurring phrases.\n\nPast scripts:\n{joined}"
    )
    return await generate_json(prompt, ToneSummary)
