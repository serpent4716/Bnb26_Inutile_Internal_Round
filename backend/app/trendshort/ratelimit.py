"""Per-provider async limiter: a serial queue (never parallel calls to one free tier),
optional fixed pacing from RATE_<PROVIDER>_RPM, and a cooldown after a 429."""
from __future__ import annotations

import asyncio
import random
import time
from collections.abc import Awaitable, Callable
from typing import TypeVar

from .config import settings

T = TypeVar("T")


class RateLimited(Exception):
    def __init__(self, provider: str, retry_after: float | None = None):
        super().__init__(f"{provider} rate-limited")
        self.provider = provider
        self.retry_after = retry_after


class TransientError(Exception):
    """Network blips / 5xx. Worth retrying."""


class ProviderUnavailable(Exception):
    """Missing key, binary, package or unreachable service. Skip to next provider, don't retry."""


class ProviderLimiter:
    def __init__(self, name: str) -> None:
        self.name = name
        self._lock = asyncio.Lock()
        self._last = 0.0
        self.cooldown_until = 0.0

    @property
    def is_rate_limited(self) -> bool:
        return time.monotonic() < self.cooldown_until

    async def run(self, fn: Callable[[], Awaitable[T]]) -> T:
        async with self._lock:  # request queue: one in-flight call per provider
            rpm = settings.rate_limit_rpm(self.name)
            wait = max(0.0, self.cooldown_until - time.monotonic())
            if rpm > 0:
                wait = max(wait, self._last + 60.0 / rpm - time.monotonic())
            if wait > 0:
                await asyncio.sleep(wait)
            try:
                return await fn()
            except RateLimited as e:
                self.cooldown_until = time.monotonic() + (e.retry_after or 10.0)
                raise
            finally:
                self._last = time.monotonic()


_limiters: dict[str, ProviderLimiter] = {}


def limiter(name: str) -> ProviderLimiter:
    if name not in _limiters:
        _limiters[name] = ProviderLimiter(name)
    return _limiters[name]


async def with_backoff(fn: Callable[[], Awaitable[T]], *, attempts: int = 3, base: float = 1.5,
                       max_wait: float = 30.0) -> T:
    """Exponential backoff with jitter for RateLimited/TransientError. Anything else propagates."""
    for i in range(attempts):
        try:
            return await fn()
        except (RateLimited, TransientError) as e:
            if i == attempts - 1:
                raise
            hint = getattr(e, "retry_after", None)
            delay = min(max_wait, hint or base * (2 ** i)) + random.uniform(0, 0.5)
            await asyncio.sleep(delay)
    raise RuntimeError("unreachable")


def raise_for_status(provider: str, status: int, headers: dict | None = None, body: str = "") -> None:
    if status == 429:
        ra = None
        if headers and headers.get("retry-after"):
            try:
                ra = float(headers["retry-after"])
            except ValueError:
                pass
        raise RateLimited(provider, ra)
    if status in (401, 403):
        raise ProviderUnavailable(f"{provider}: auth failed ({status}). Check the API key. {body[:200]}")
    if status >= 500:
        raise TransientError(f"{provider}: HTTP {status}")
    if status >= 400:
        raise ProviderUnavailable(f"{provider}: HTTP {status} {body[:300]}")
