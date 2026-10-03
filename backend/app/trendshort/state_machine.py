"""Run state machine + stage dependency graph (used for stale propagation)."""
from __future__ import annotations

PIPELINE_STATES = ["trend_selected", "scripting", "voicing", "sourcing_visuals", "assembling",
                   "ready_for_review", "publishing", "published"]
STATES = PIPELINE_STATES + ["failed"]

# Executable stages in order, and the run state each one maps to.
STAGES = ["script", "audio", "visuals", "assembly"]
STAGE_STATE = {"script": "scripting", "audio": "voicing", "visuals": "sourcing_visuals",
               "assembly": "assembling", "publish": "publishing"}

# Upstream -> direct downstream dependents. Visuals depend on audio because audio drives scene timing.
DEPENDENTS: dict[str, list[str]] = {
    "script": ["audio", "visuals"],
    "audio": ["visuals", "assembly"],
    "visuals": ["assembly"],
    "assembly": [],
}

_FORWARD = {a: b for a, b in zip(PIPELINE_STATES, PIPELINE_STATES[1:])}


class InvalidTransition(ValueError):
    pass


def can_transition(current: str, new: str) -> bool:
    if current not in STATES or new not in STATES:
        return False
    if new == "failed":
        return current != "published"
    if _FORWARD.get(current) == new:
        return True
    # Rewind: re-running a stage or editing upstream output from review/failed/published-preview.
    if current in {"failed", "ready_for_review", "published"} or current in STAGE_STATE.values():
        if new in {"scripting", "voicing", "sourcing_visuals", "assembling"}:
            return current == "failed" or PIPELINE_STATES.index(new) <= PIPELINE_STATES.index(current)
    # Re-publish from published (e.g. a dry run first, then real upload).
    if current == "published" and new == "publishing":
        return True
    if current == "failed" and new in {"ready_for_review", "publishing"}:
        return True
    return False


def transition(current: str, new: str) -> str:
    if not can_transition(current, new):
        raise InvalidTransition(f"cannot go from {current!r} to {new!r}")
    return new


def downstream(stage: str) -> list[str]:
    """All transitive dependents of a stage, in pipeline order."""
    seen: set[str] = set()
    stack = list(DEPENDENTS.get(stage, []))
    while stack:
        s = stack.pop()
        if s not in seen:
            seen.add(s)
            stack.extend(DEPENDENTS.get(s, []))
    return [s for s in STAGES if s in seen]
