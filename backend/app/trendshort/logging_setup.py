"""Structured JSON logging with a per-run context; each run also gets its own run.log file."""
from __future__ import annotations

import contextvars
import json
import logging
import sys
import time

from .config import settings

current_run: contextvars.ContextVar[str | None] = contextvars.ContextVar("current_run", default=None)
current_stage: contextvars.ContextVar[str | None] = contextvars.ContextVar("current_stage", default=None)


class JsonFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        payload = {
            "ts": time.strftime("%Y-%m-%dT%H:%M:%S", time.localtime(record.created)),
            "level": record.levelname.lower(),
            "logger": record.name,
            "msg": record.getMessage(),
            "run_id": current_run.get(),
            "stage": current_stage.get(),
        }
        extra = getattr(record, "data", None)
        if extra:
            payload.update(extra)
        if record.exc_info:
            payload["exc"] = self.formatException(record.exc_info)
        return json.dumps({k: v for k, v in payload.items() if v is not None}, default=str)


class RunFileHandler(logging.Handler):
    """Appends every record that carries a run_id to data/runs/<id>/run.log."""

    def __init__(self) -> None:
        super().__init__()
        self.setFormatter(JsonFormatter())

    def emit(self, record: logging.LogRecord) -> None:
        run_id = current_run.get()
        if not run_id:
            return
        d = settings.runs_dir / run_id
        d.mkdir(parents=True, exist_ok=True)
        with open(d / "run.log", "a", encoding="utf-8") as f:
            f.write(self.format(record) + "\n")


def setup_logging() -> None:
    """Scoped to the "t2s" logger tree so CreatorAi's/uvicorn's own logging is left untouched."""
    root = logging.getLogger("t2s")
    if getattr(root, "_tts_configured", False):
        return
    root.setLevel(logging.INFO)
    out = logging.StreamHandler(sys.stdout)
    out.setFormatter(JsonFormatter())
    root.handlers = [out, RunFileHandler()]
    root.propagate = False
    for noisy in ("httpx", "httpcore", "faster_whisper"):
        logging.getLogger(noisy).setLevel(logging.WARNING)
    root._tts_configured = True  # type: ignore[attr-defined]


def log(logger: logging.Logger, msg: str, level: int = logging.INFO, **data) -> None:
    logger.log(level, msg, extra={"data": data})
