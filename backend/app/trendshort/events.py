"""In-process pub/sub for SSE progress events."""
from __future__ import annotations

import asyncio
import time
from collections import defaultdict
from typing import Any


class EventBus:
    def __init__(self) -> None:
        self._subs: dict[str, set[asyncio.Queue]] = defaultdict(set)

    def subscribe(self, run_id: str) -> asyncio.Queue:
        q: asyncio.Queue = asyncio.Queue(maxsize=500)
        self._subs[run_id].add(q)
        return q

    def unsubscribe(self, run_id: str, q: asyncio.Queue) -> None:
        self._subs[run_id].discard(q)

    def publish(self, run_id: str, event: str, data: dict[str, Any]) -> None:
        msg = {"event": event, "ts": time.time(), **data}
        for q in list(self._subs.get(run_id, ())):
            try:
                q.put_nowait(msg)
            except asyncio.QueueFull:
                pass


bus = EventBus()
