"""Collects which provider answered each sub-call, fallbacks taken, and free-tier usage, per stage."""
from __future__ import annotations

import contextvars
from dataclasses import dataclass, field


@dataclass
class StageTracker:
    providers: list[dict] = field(default_factory=list)   # [{"call": "script.hook", "provider": "ollama", "cached": False}]
    fallbacks: list[str] = field(default_factory=list)    # ["gemini: missing key GEMINI_API_KEY", ...]
    cost: dict = field(default_factory=lambda: {"llm_tokens_est": 0, "tts_chars": 0, "api_requests": 0, "usd": 0.0})
    all_cached: bool = True

    def used(self, call: str, provider: str, cached: bool = False) -> None:
        self.providers.append({"call": call, "provider": provider, "cached": cached})
        if not cached:
            self.all_cached = False

    def fell_back(self, note: str) -> None:
        if note not in self.fallbacks:
            self.fallbacks.append(note)

    def add(self, key: str, n: float) -> None:
        self.cost[key] = self.cost.get(key, 0) + n


current_tracker: contextvars.ContextVar[StageTracker | None] = contextvars.ContextVar("tracker", default=None)


def tracker() -> StageTracker:
    t = current_tracker.get()
    if t is None:          # outside a stage (e.g. /trends): use a throwaway tracker
        t = StageTracker()
        current_tracker.set(t)
    return t


# Set by explicit "re-run" so the user gets a fresh result instead of the cached one.
bypass_cache: contextvars.ContextVar[bool] = contextvars.ContextVar("bypass_cache", default=False)
