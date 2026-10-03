"""On-disk cache keyed by a hash of the stage/provider input, so demo re-runs cost zero quota."""
from __future__ import annotations

import hashlib
import json
import time
from pathlib import Path
from typing import Any

from .config import settings


def stable_hash(obj: Any) -> str:
    raw = json.dumps(obj, sort_keys=True, default=str, ensure_ascii=False)
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()[:24]


class DiskCache:
    def __init__(self, namespace: str) -> None:
        self.dir = settings.cache_dir / namespace
        self.dir.mkdir(parents=True, exist_ok=True)

    def path_for(self, key: str, suffix: str = ".json") -> Path:
        return self.dir / f"{key}{suffix}"

    def get(self, key: str, ttl_seconds: float | None = None) -> Any | None:
        p = self.path_for(key)
        if not p.exists():
            return None
        if ttl_seconds is not None and time.time() - p.stat().st_mtime > ttl_seconds:
            return None
        try:
            data = json.loads(p.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            return None
        # Entries referencing files are only valid while those files exist.
        for f in data.get("_files", []) if isinstance(data, dict) else []:
            if not Path(f).exists():
                return None
        return data

    def set(self, key: str, value: Any, files: list[str] | None = None) -> None:
        if files and isinstance(value, dict):
            value = {**value, "_files": files}
        tmp = self.path_for(key, ".tmp")
        tmp.write_text(json.dumps(value, default=str, ensure_ascii=False), encoding="utf-8")
        tmp.replace(self.path_for(key))
