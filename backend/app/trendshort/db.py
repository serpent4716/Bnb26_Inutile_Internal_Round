"""SQLite persistence: runs, per-stage records (inputs/outputs/provider/cost), cached trend ideas."""
from __future__ import annotations

import json
import uuid
from datetime import datetime, timezone
from typing import Any

from sqlalchemy import JSON, Boolean, DateTime, Float, ForeignKey, Integer, String, Text, create_engine
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship, sessionmaker

from .config import settings

engine = create_engine(settings.db_url, connect_args={"check_same_thread": False}, future=True)
SessionLocal = sessionmaker(bind=engine, expire_on_commit=False, future=True)


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


class Base(DeclarativeBase):
    pass


class Run(Base):
    __tablename__ = "runs"
    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=lambda: uuid.uuid4().hex[:12])
    user_id: Mapped[str | None] = mapped_column(String(32), nullable=True, index=True)   # CreatorAi user (Mongo id)
    project_id: Mapped[str | None] = mapped_column(String(32), nullable=True)            # set by "Save to CreatorAi"
    trend_id: Mapped[str] = mapped_column(String(64))
    idea: Mapped[dict] = mapped_column(JSON)
    mode: Mapped[str] = mapped_column(String(8), default="review")
    voice_profile: Mapped[str | None] = mapped_column(Text, nullable=True)
    state: Mapped[str] = mapped_column(String(32), default="trend_selected")
    awaiting_approval: Mapped[bool] = mapped_column(Boolean, default=False)
    next_stage: Mapped[str | None] = mapped_column(String(16), nullable=True)
    edl_override: Mapped[dict | None] = mapped_column(JSON, nullable=True)   # user-edited EDL (render-only)
    failed_stage: Mapped[str | None] = mapped_column(String(16), nullable=True)
    error: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, onupdate=utcnow)
    stages: Mapped[list["StageRecord"]] = relationship(back_populates="run", cascade="all, delete-orphan",
                                                       order_by="StageRecord.id")


class StageRecord(Base):
    __tablename__ = "stages"
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    run_id: Mapped[str] = mapped_column(ForeignKey("runs.id"))
    stage: Mapped[str] = mapped_column(String(16))
    status: Mapped[str] = mapped_column(String(12), default="pending")   # pending|running|done|failed|stale
    input_hash: Mapped[str | None] = mapped_column(String(32), nullable=True)
    input: Mapped[Any] = mapped_column(JSON, nullable=True)
    output: Mapped[Any] = mapped_column(JSON, nullable=True)
    providers: Mapped[list] = mapped_column(JSON, default=list)       # which provider answered each sub-call
    fallbacks: Mapped[list] = mapped_column(JSON, default=list)       # human-readable fallback notes
    attempts: Mapped[int] = mapped_column(Integer, default=0)
    duration_ms: Mapped[float] = mapped_column(Float, default=0)
    cost: Mapped[dict] = mapped_column(JSON, default=dict)            # tokens/characters/requests, all free
    cached: Mapped[bool] = mapped_column(Boolean, default=False)
    error: Mapped[str | None] = mapped_column(Text, nullable=True)
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    run: Mapped[Run] = relationship(back_populates="stages")


class TrendIdeaRow(Base):
    __tablename__ = "trend_ideas"
    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    data: Mapped[dict] = mapped_column(JSON)
    fetched_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


def init_db() -> None:
    Base.metadata.create_all(engine)


def stage_dict(s: StageRecord) -> dict:
    return {
        "stage": s.stage, "status": s.status, "output": s.output, "providers": s.providers,
        "fallbacks": s.fallbacks, "attempts": s.attempts, "duration_ms": round(s.duration_ms),
        "cost": s.cost, "cached": s.cached, "error": s.error, "input_hash": s.input_hash,
        "started_at": s.started_at.isoformat() if s.started_at else None,
        "finished_at": s.finished_at.isoformat() if s.finished_at else None,
    }


def run_dict(r: Run) -> dict:
    return {
        "id": r.id, "user_id": r.user_id, "project_id": r.project_id, "trend_id": r.trend_id, "idea": r.idea, "mode": r.mode, "state": r.state,
        "awaiting_approval": r.awaiting_approval, "next_stage": r.next_stage,
        "failed_stage": r.failed_stage, "error": r.error, "edl_edited": r.edl_override is not None,
        "created_at": r.created_at.isoformat(), "updated_at": r.updated_at.isoformat() if r.updated_at else None,
        "stages": {s.stage: stage_dict(s) for s in r.stages},
    }


def dumps(obj: Any) -> str:
    return json.dumps(obj, default=str)
