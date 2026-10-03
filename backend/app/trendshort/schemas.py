"""Pydantic schemas for every agent input/output, the EDL, and the API."""
from __future__ import annotations

from enum import Enum
from typing import Literal

from pydantic import BaseModel, Field, field_validator, model_validator

# ---------------------------------------------------------------- trends

class TrendItem(BaseModel):
    id: str
    title: str
    source: Literal["youtube", "google_trends", "reddit", "mock"]
    region: str = "US"
    category: str = "general"
    momentum_score: float = Field(ge=0, le=100)
    sample_urls: list[str] = []


class ShortIdea(BaseModel):
    id: str
    title: str
    hook_angle: str
    why_trending: str
    target_platform: Literal["youtube_shorts", "tiktok", "instagram_reels"] = "youtube_shorts"
    estimated_length_sec: int = Field(ge=15, le=60)
    category: str = "general"
    region: str = "US"
    momentum_score: float = 0
    sources: list[str] = []
    sample_urls: list[str] = []
    trend_ids: list[str] = []


# LLM output shape for clustering (kept small for weak free models)
class _ClusterIdea(BaseModel):
    trend_ids: list[str] = Field(min_length=1)
    title: str = Field(min_length=3)
    hook_angle: str = Field(min_length=3)
    why_trending: str = Field(min_length=3)
    target_platform: Literal["youtube_shorts", "tiktok", "instagram_reels"] = "youtube_shorts"
    estimated_length_sec: int = Field(default=30, ge=15, le=60)
    category: str = "general"


class ClusterOutput(BaseModel):
    ideas: list[_ClusterIdea] = Field(min_length=1)


# ---------------------------------------------------------------- script

HOOK_MAX_WORDS = 10           # ~3s of speech at a brisk pace
SCRIPT_MIN_SEC, SCRIPT_MAX_SEC = 20, 45


class Scene(BaseModel):
    id: str
    narration: str = Field(min_length=2, max_length=400)
    visual_query: str = Field(min_length=2, max_length=80)
    on_screen_text: str = Field(default="", max_length=60)
    duration_sec: float = Field(gt=0, le=15)


class ScriptOutput(BaseModel):
    title: str = Field(min_length=3, max_length=100)
    hook: str = Field(min_length=2)
    scenes: list[Scene] = Field(min_length=3, max_length=10)
    cta: str = Field(min_length=2, max_length=120)
    hashtags: list[str] = Field(min_length=1, max_length=10)
    description: str = Field(min_length=5, max_length=1500)

    @field_validator("hashtags")
    @classmethod
    def _tags(cls, v: list[str]) -> list[str]:
        out = []
        for t in v:
            t = "#" + t.strip().lstrip("#").replace(" ", "")
            if len(t) > 1 and t.lower() not in {x.lower() for x in out}:
                out.append(t)
        if not out:
            raise ValueError("at least one non-empty hashtag required")
        return out

    @field_validator("hook")
    @classmethod
    def _hook_short(cls, v: str) -> str:
        if len(v.split()) > HOOK_MAX_WORDS:
            raise ValueError(f"hook must be <= {HOOK_MAX_WORDS} words so it lands in the first 3 seconds")
        return v.strip()

    @model_validator(mode="after")
    def _structure(self) -> "ScriptOutput":
        ids = [s.id for s in self.scenes]
        if len(set(ids)) != len(ids):
            raise ValueError("scene ids must be unique")
        if self.scenes[0].narration.strip().lower() != self.hook.strip().lower():
            raise ValueError("scene 1 narration must be exactly the hook")
        total = sum(s.duration_sec for s in self.scenes)
        if not (SCRIPT_MIN_SEC <= total <= SCRIPT_MAX_SEC):
            raise ValueError(f"total duration {total:.1f}s outside {SCRIPT_MIN_SEC}-{SCRIPT_MAX_SEC}s")
        return self

    @property
    def total_duration(self) -> float:
        return sum(s.duration_sec for s in self.scenes)


# Small per-call shapes (hook -> scenes -> packaging)
class HookPart(BaseModel):
    title: str = Field(min_length=3, max_length=100)
    hook: str = Field(min_length=2)

    @field_validator("hook")
    @classmethod
    def _short(cls, v: str) -> str:
        if len(v.split()) > HOOK_MAX_WORDS:
            raise ValueError(f"hook must be <= {HOOK_MAX_WORDS} words")
        return v.strip()


class _SceneDraft(BaseModel):
    narration: str = Field(min_length=2, max_length=400)
    visual_query: str = Field(min_length=2, max_length=80)


class ScenesPart(BaseModel):
    scenes: list[_SceneDraft] = Field(min_length=3, max_length=8)


class PackagingPart(BaseModel):
    on_screen_text: list[str]
    cta: str = Field(min_length=2, max_length=120)
    hashtags: list[str] = Field(min_length=1, max_length=10)
    description: str = Field(min_length=5, max_length=1500)


class ScriptInput(BaseModel):
    idea: ShortIdea
    voice_profile: str | None = None


# ---------------------------------------------------------------- audio

class WordStamp(BaseModel):
    word: str
    start: float = Field(ge=0)
    end: float = Field(ge=0)


class SceneAudio(BaseModel):
    scene_id: str
    path: str
    duration_sec: float = Field(gt=0)
    words: list[WordStamp] = []          # relative to scene start
    tts_provider: str
    caption_provider: str


class AudioOutput(BaseModel):
    scenes: list[SceneAudio]
    total_duration: float


# ---------------------------------------------------------------- visuals

class Attribution(BaseModel):
    provider: str
    author: str = ""
    author_url: str = ""
    source_url: str = ""
    license: str = ""


class ClipCandidate(BaseModel):
    kind: Literal["video", "image"]
    provider: str
    url: str                         # download URL
    preview_url: str = ""
    description: str = ""
    width: int = 0
    height: int = 0
    duration_sec: float = 0
    attribution: Attribution
    local_path: str | None = None


class SceneVisual(BaseModel):
    scene_id: str
    chosen_index: int = 0
    candidates: list[ClipCandidate] = Field(min_length=1)

    @property
    def chosen(self) -> ClipCandidate:
        return self.candidates[self.chosen_index]


class VisualOutput(BaseModel):
    scenes: list[SceneVisual]
    ranking_provider: str


class VisualRanking(BaseModel):
    """Batched LLM output: best candidate index per scene."""
    picks: list[dict[str, int | str]]   # [{"scene_id": "s1", "best": 0}]


class VisualSwap(BaseModel):
    scene_id: str
    candidate_index: int = Field(ge=0)


# ---------------------------------------------------------------- EDL

class EDLSource(BaseModel):
    kind: Literal["video", "image"]
    path: str
    in_point: float = 0.0
    ken_burns: bool = False


class EDLVideoSegment(BaseModel):
    scene_id: str
    start: float = Field(ge=0)
    duration: float = Field(gt=0)
    source: EDLSource
    attribution: Attribution


class EDLAudioSegment(BaseModel):
    scene_id: str
    start: float = Field(ge=0)
    duration: float = Field(gt=0)
    path: str


class EDLMusic(BaseModel):
    path: str
    volume: float = Field(default=0.25, ge=0, le=1)
    duck: bool = True
    attribution: Attribution | None = None


class EDLCaptionStyle(BaseModel):
    font: str = "Poppins"
    size: int = 82
    primary_color: str = "&H0000E5FF"     # ASS &HAABBGGRR, highlighted word (warm yellow)
    secondary_color: str = "&H00FFFFFF"   # not-yet-spoken words
    outline_color: str = "&H00000000"
    words_per_line: int = 3
    margin_v: int = 520


class EDLOverlay(BaseModel):
    text: str
    start: float = Field(ge=0)
    end: float = Field(gt=0)
    position: Literal["top", "center", "bottom"] = "top"
    kind: Literal["hook", "scene_text"] = "scene_text"


class EDL(BaseModel):
    version: int = 1
    run_id: str
    width: int = 1080
    height: int = 1920
    fps: int = 30
    total_duration: float = Field(gt=0)
    video: list[EDLVideoSegment] = Field(min_length=1)
    voice: list[EDLAudioSegment] = Field(min_length=1)
    music: EDLMusic | None = None
    caption_style: EDLCaptionStyle = EDLCaptionStyle()
    words: list[WordStamp] = []          # absolute times
    overlays: list[EDLOverlay] = []

    @model_validator(mode="after")
    def _contiguous(self) -> "EDL":
        t = 0.0
        for seg in self.video:
            if abs(seg.start - t) > 0.05:
                raise ValueError(f"video segment {seg.scene_id} starts at {seg.start}, expected {t:.3f}")
            t += seg.duration
        if abs(t - self.total_duration) > 0.1:
            raise ValueError("video track length must equal total_duration")
        return self


class AssemblyOutput(BaseModel):
    edl: EDL
    video_path: str
    ass_path: str
    render_seconds: float


# ---------------------------------------------------------------- publish

class PublishTarget(str, Enum):
    youtube = "youtube"
    export = "export"           # TikTok / Instagram package, never auto-posted


class PublishRequest(BaseModel):
    target: PublishTarget
    dry_run: bool = True
    title: str | None = None
    description: str | None = None
    hashtags: list[str] | None = None


class PublishOutput(BaseModel):
    target: PublishTarget
    dry_run: bool
    url: str | None = None
    export_dir: str | None = None
    files: list[str] = []
    privacy: str | None = None
    notice: str = ""


# ---------------------------------------------------------------- API

class RunCreate(BaseModel):
    trend_id: str
    mode: Literal["review", "auto"] = "review"
    voice_profile: str | None = None


class ScriptPatch(BaseModel):
    script: ScriptOutput
