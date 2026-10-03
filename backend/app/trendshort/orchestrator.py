"""Run orchestration: state machine, per-stage persistence, caching by input hash, retries,
stale propagation, review-mode pauses, and SSE events."""
from __future__ import annotations

import asyncio
import logging
import time
import traceback
from typing import Any

from sqlalchemy import select

from .agents import assembly_agent, audio_agent, publish_agent, script_agent, visual_agent
from .cache import DiskCache, stable_hash
from .db import Run, SessionLocal, StageRecord, run_dict, stage_dict, utcnow
from .events import bus
from .logging_setup import current_run, current_stage, log
from .schemas import (EDL, AssemblyOutput, AudioOutput, PublishOutput, PublishRequest, ScriptInput, ScriptOutput,
                      ShortIdea, VisualOutput, VisualSwap)
from .state_machine import STAGE_STATE, STAGES, downstream, transition
from .tracking import StageTracker, bypass_cache, current_tracker

logger = logging.getLogger("t2s.orchestrator")
_stage_cache = DiskCache("stages")
_locks: dict[str, asyncio.Lock] = {}
_tasks: dict[str, asyncio.Task] = {}
STAGE_RETRIES = 2
CACHEABLE = {"script", "audio", "visuals"}


def _lock(run_id: str) -> asyncio.Lock:
    return _locks.setdefault(run_id, asyncio.Lock())


# ------------------------------------------------------------------ db helpers

def create_run(idea: ShortIdea, mode: str, voice_profile: str | None, user_id: str | None = None) -> dict:
    with SessionLocal() as db:
        r = Run(user_id=user_id, trend_id=idea.id, idea=idea.model_dump(), mode=mode, voice_profile=voice_profile)
        r.stages = [StageRecord(stage=s) for s in STAGES + ["publish"]]
        db.add(r)
        db.commit()
        db.refresh(r)
        return run_dict(r)


def list_runs(user_id: str, limit: int = 50) -> list[dict]:
    with SessionLocal() as db:
        rows = db.scalars(select(Run).where(Run.user_id == user_id).order_by(Run.created_at.desc()).limit(limit))
        return [run_dict(r) for r in rows]


def set_project(run_id: str, project_id: str) -> None:
    with SessionLocal() as db:
        r = db.get(Run, run_id)
        r.project_id = project_id
        db.commit()


def get_run(run_id: str) -> dict | None:
    with SessionLocal() as db:
        r = db.get(Run, run_id)
        return run_dict(r) if r else None


def _load(db, run_id: str) -> tuple[Run, dict[str, StageRecord]]:
    r = db.get(Run, run_id)
    if r is None:
        raise KeyError(run_id)
    return r, {s.stage: s for s in r.stages}


def _emit_run(run_id: str) -> None:
    d = get_run(run_id)
    if d:
        bus.publish(run_id, "run", {"run": d})


def _emit_stage(run_id: str, st: StageRecord) -> None:
    bus.publish(run_id, "stage", {"stage": stage_dict(st)})


def _set_state(r: Run, new: str) -> None:
    if r.state != new:
        r.state = transition(r.state, new)


def _mark_stale(db, stages: dict[str, StageRecord], changed: str, run: Run) -> list[str]:
    marked = []
    for d in downstream(changed):
        if stages[d].status in ("done", "failed"):
            stages[d].status = "stale"
            marked.append(d)
        if d == "assembly":
            run.edl_override = None       # an upstream change invalidates manual EDL edits
    return marked


# ------------------------------------------------------------------ stage execution

def _inputs(stage: str, run: Run, stages: dict[str, StageRecord]) -> dict[str, Any]:
    out = lambda s: stages[s].output  # noqa: E731
    if stage == "script":
        return {"idea": run.idea, "voice_profile": run.voice_profile}
    if stage == "audio":
        return {"script": out("script")}
    if stage == "visuals":
        return {"script": out("script"), "audio": out("audio")}
    if stage == "assembly":
        return {"script": out("script"), "audio": out("audio"), "visuals": out("visuals"),
                "edl_override": run.edl_override}
    raise ValueError(stage)


def _check_ready(stage: str, stages: dict[str, StageRecord]) -> None:
    need = {"audio": ["script"], "visuals": ["script", "audio"], "assembly": ["script", "audio", "visuals"]}
    for up in need.get(stage, []):
        if stages[up].status != "done":
            raise RuntimeError(f"Cannot run {stage}: upstream stage {up!r} is {stages[up].status}. Run it first.")


async def _call_agent(stage: str, run_id: str, inp: dict) -> tuple[dict, list[str]]:
    if stage == "script":
        out, _ = await script_agent.run(ScriptInput(idea=ShortIdea.model_validate(inp["idea"]),
                                                    voice_profile=inp["voice_profile"]))
        return out.model_dump(), []
    if stage == "audio":
        out = await audio_agent.run(run_id, ScriptOutput.model_validate(inp["script"]))
        return out.model_dump(), [a.path for a in out.scenes]
    if stage == "visuals":
        out = await visual_agent.run(ScriptOutput.model_validate(inp["script"]),
                                     AudioOutput.model_validate(inp["audio"]))
        return out.model_dump(), [s.chosen.local_path for s in out.scenes if s.chosen.local_path]
    if stage == "assembly":
        override = EDL.model_validate(inp["edl_override"]) if inp.get("edl_override") else None
        out = await assembly_agent.run(run_id, ScriptOutput.model_validate(inp["script"]),
                                       AudioOutput.model_validate(inp["audio"]),
                                       VisualOutput.model_validate(inp["visuals"]), override)
        return out.model_dump(), [out.video_path]
    raise ValueError(stage)


async def execute_stage(run_id: str, stage: str, fresh: bool = False) -> bool:
    """Run one stage. Returns True on success. Never raises for agent failures (records them)."""
    current_run.set(run_id)
    current_stage.set(stage)
    tr = StageTracker()
    current_tracker.set(tr)
    bypass_cache.set(fresh)
    with SessionLocal() as db:
        run, stages = _load(db, run_id)
        st = stages[stage]
        _check_ready(stage, stages)
        _set_state(run, STAGE_STATE[stage])
        run.awaiting_approval, run.next_stage, run.error, run.failed_stage = False, None, None, None
        inp = _inputs(stage, run, stages)
        st.status, st.started_at, st.error, st.attempts = "running", utcnow(), None, 0
        st.input, st.input_hash = inp, stable_hash({"stage": stage, **inp})
        prev_output_hash = stable_hash(st.output) if st.output else None
        db.commit()
        _emit_stage(run_id, st)
        _emit_run(run_id)
        input_hash = st.input_hash

    log(logger, "stage started", input_hash=input_hash, fresh=fresh)
    t0 = time.monotonic()
    output, error, cached = None, None, False
    if stage in CACHEABLE and not fresh and (hit := _stage_cache.get(input_hash)):
        output, cached = hit["output"], True
        tr.providers, tr.fallbacks = hit.get("providers", []), hit.get("fallbacks", [])
        tr.used(f"{stage}.stage_cache", "disk-cache", cached=True)
    else:
        for attempt in range(1, STAGE_RETRIES + 1):
            try:
                with SessionLocal() as db:
                    db.get(StageRecord, st.id).attempts = attempt
                    db.commit()
                output, files = await _call_agent(stage, run_id, inp)
                if stage in CACHEABLE:
                    _stage_cache.set(input_hash, {"output": output, "providers": tr.providers,
                                                  "fallbacks": tr.fallbacks}, files=files)
                break
            except Exception as e:  # noqa: BLE001 - recorded on the run, never crashes the server
                error = f"{type(e).__name__}: {e}"
                log(logger, "stage attempt failed", logging.WARNING, attempt=attempt, error=error[:500],
                    tb=traceback.format_exc(limit=4))
                if attempt < STAGE_RETRIES:
                    await asyncio.sleep(2 ** attempt)

    with SessionLocal() as db:
        run, stages = _load(db, run_id)
        st = stages[stage]
        st.duration_ms = (time.monotonic() - t0) * 1000
        st.finished_at = utcnow()
        st.providers, st.fallbacks, st.cost, st.cached = tr.providers, tr.fallbacks, tr.cost, cached or (
            tr.all_cached and bool(tr.providers))
        if output is None:
            st.status, st.error = "failed", error
            _set_state(run, "failed")
            run.failed_stage, run.error = stage, error
            db.commit()
            log(logger, "stage failed", logging.ERROR, error=error)
        else:
            st.status, st.output = "done", output
            if stable_hash(output) != prev_output_hash:
                if marked := _mark_stale(db, stages, stage, run):
                    log(logger, "downstream marked stale", stages=marked)
            db.commit()
            used = sorted({p["provider"] for p in tr.providers})
            log(logger, "stage done", providers=used, fallbacks=tr.fallbacks, cached=st.cached,
                duration_ms=round(st.duration_ms), cost=tr.cost)
        _emit_stage(run_id, st)
    _emit_run(run_id)
    return output is not None


async def drive(run_id: str, start_at: str | None = None, fresh_first: bool = False) -> None:
    """Advance the pipeline. Auto mode runs to ready_for_review; review mode pauses after each stage."""
    async with _lock(run_id):
        current_run.set(run_id)
        idx = STAGES.index(start_at) if start_at else 0
        for i, stage in enumerate(STAGES[idx:], start=idx):
            with SessionLocal() as db:
                run, stages = _load(db, run_id)
                mode, status = run.mode, stages[stage].status
            if status == "done" and not (fresh_first and i == idx):
                continue
            ok = await execute_stage(run_id, stage, fresh=fresh_first and i == idx)
            if not ok:
                return
            nxt = next((s for s in STAGES[i + 1:]), None)
            with SessionLocal() as db:
                run, stages = _load(db, run_id)
                if nxt is None or all(stages[s].status == "done" for s in STAGES[i + 1:]):
                    _set_state(run, "ready_for_review")
                    run.awaiting_approval, run.next_stage = False, None
                    db.commit()
                    _emit_run(run_id)
                    log(logger, "run ready for review")
                    return
                if mode == "review":
                    run.awaiting_approval = True
                    run.next_stage = next(s for s in STAGES[i + 1:] if stages[s].status != "done")
                    db.commit()
                    _emit_run(run_id)
                    return


def start(run_id: str, start_at: str | None = None, fresh_first: bool = False) -> None:
    task = asyncio.create_task(drive(run_id, start_at, fresh_first))
    _tasks[run_id] = task
    task.add_done_callback(lambda t: not t.cancelled() and t.exception() and log(logger, "drive crashed", logging.ERROR,
                                                           error=str(t.exception())))


def is_busy(run_id: str) -> bool:
    return _lock(run_id).locked()


# ------------------------------------------------------------------ user actions

def approve(run_id: str) -> dict:
    with SessionLocal() as db:
        run, stages = _load(db, run_id)
        nxt = run.next_stage or next((s for s in STAGES if stages[s].status != "done"), None)
    if nxt:
        start(run_id, nxt)
    return get_run(run_id)


def set_mode(run_id: str, mode: str) -> dict:
    with SessionLocal() as db:
        run, _ = _load(db, run_id)
        run.mode = mode
        db.commit()
        waiting = run.awaiting_approval
    if mode == "auto" and waiting:
        return approve(run_id)
    _emit_run(run_id)
    return get_run(run_id)


def _after_edit(run_id: str, changed: str) -> dict:
    with SessionLocal() as db:
        run, stages = _load(db, run_id)
        _mark_stale(db, stages, changed, run)
        target = STAGE_STATE[changed]
        if run.state != target:
            _set_state(run, target)
        nxt = next((s for s in STAGES if stages[s].status != "done"), None)
        run.awaiting_approval, run.next_stage = nxt is not None, nxt
        mode = run.mode
        db.commit()
        for s in stages.values():
            _emit_stage(run_id, s)
    _emit_run(run_id)
    if mode == "auto" and nxt:
        start(run_id, nxt)
    return get_run(run_id)


def patch_script(run_id: str, script: ScriptOutput) -> dict:
    with SessionLocal() as db:
        run, stages = _load(db, run_id)
        st = stages["script"]
        st.output, st.status = script.model_dump(), "done"
        st.providers = (st.providers or []) + [{"call": "script.edit", "provider": "user-edit", "cached": False}]
        db.commit()
    log(logger, "script edited by user")
    return _after_edit(run_id, "script")


def swap_visual(run_id: str, swap: VisualSwap) -> dict:
    with SessionLocal() as db:
        run, stages = _load(db, run_id)
        vo = VisualOutput.model_validate(stages["visuals"].output)
        for i, sv in enumerate(vo.scenes):
            if sv.scene_id == swap.scene_id:
                if swap.candidate_index >= len(sv.candidates):
                    raise ValueError("candidate_index out of range")
                vo.scenes[i] = sv.model_copy(update={"chosen_index": swap.candidate_index})
                break
        else:
            raise ValueError(f"unknown scene {swap.scene_id}")
    return vo


async def apply_visual_swap(run_id: str, swap: VisualSwap) -> dict:
    vo = swap_visual(run_id, swap)
    i = next(i for i, s in enumerate(vo.scenes) if s.scene_id == swap.scene_id)
    vo.scenes[i] = await visual_agent.ensure_downloaded(vo.scenes[i])
    with SessionLocal() as db:
        run, stages = _load(db, run_id)
        stages["visuals"].output = vo.model_dump()
        db.commit()
    return _after_edit(run_id, "visuals")


def patch_edl(run_id: str, edl: EDL) -> dict:
    if edl.run_id != run_id:
        raise ValueError("EDL run_id does not match this run")
    with SessionLocal() as db:
        run, stages = _load(db, run_id)
        if stages["assembly"].status not in ("done", "stale", "failed"):
            raise ValueError("Assemble the video before editing the EDL")
        run.edl_override = edl.model_dump()
        stages["assembly"].status = "stale"
        if run.state != "assembling":
            _set_state(run, "assembling")
        db.commit()
    log(logger, "EDL edited by user; re-rendering without LLM/TTS calls")
    start(run_id, "assembly")
    return get_run(run_id)


def rerun(run_id: str, stage: str) -> dict:
    if stage not in STAGES:
        raise ValueError(f"unknown stage {stage}")
    with SessionLocal() as db:
        _check_ready(stage, _load(db, run_id)[1])
    start(run_id, stage, fresh_first=True)
    return get_run(run_id)


async def publish(run_id: str, req: PublishRequest) -> PublishOutput:
    current_run.set(run_id)
    current_stage.set("publish")
    async with _lock(run_id):
        with SessionLocal() as db:
            run, stages = _load(db, run_id)
            if stages["assembly"].status != "done":
                raise ValueError("Video is not assembled (or is stale). Re-render before publishing.")
            _set_state(run, "publishing")
            stages["publish"].status, stages["publish"].started_at = "running", utcnow()
            script = ScriptOutput.model_validate(stages["script"].output)
            asm = AssemblyOutput.model_validate(stages["assembly"].output)
            db.commit()
        _emit_run(run_id)
        try:
            out = await publish_agent.run(run_id, req, script, asm)
        except Exception as e:  # noqa: BLE001
            with SessionLocal() as db:
                run, stages = _load(db, run_id)
                stages["publish"].status, stages["publish"].error = "failed", str(e)
                _set_state(run, "failed")
                run.failed_stage, run.error = "publish", str(e)
                db.commit()
            _emit_run(run_id)
            log(logger, "publish failed", logging.ERROR, error=str(e))
            raise
        with SessionLocal() as db:
            run, stages = _load(db, run_id)
            st = stages["publish"]
            st.status, st.finished_at = "done", utcnow()
            st.output = (st.output or []) + [out.model_dump(mode="json")]
            st.providers = (st.providers or []) + [{"call": f"publish.{req.target.value}",
                                                     "provider": "dry-run" if req.dry_run and req.target.value == "youtube"
                                                     else req.target.value, "cached": False}]
            _set_state(run, "published")
            db.commit()
        _emit_run(run_id)
        log(logger, "published", target=req.target.value, dry_run=req.dry_run, url=out.url, export_dir=out.export_dir)
        return out
