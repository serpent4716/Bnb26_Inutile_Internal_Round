"""Script parsing: content -> lines, Gemini labels each line's section."""

import logging
import re
from typing import Literal

from pydantic import BaseModel

from app.db import db
from app.services import llm

log = logging.getLogger("uvicorn.error")

Section = Literal["hook", "intro", "body", "cta"]
_SENTENCE = re.compile(r"(?<=[.!?])\s+")
_BULLET = re.compile(r"^\s*(?:[-*•]|\d+[.)])\s+")


class Sections(BaseModel):
    sections: list[Section]


def parse_lines(content: str) -> list[str]:
    """One line per sentence; strips bullets and list numbering."""
    out = []
    for raw in content.splitlines():
        out += [s.strip() for s in _SENTENCE.split(_BULLET.sub("", raw).strip()) if s.strip()]
    return out


def fallback_sections(n: int) -> list[str]:
    return ["hook"] + ["body"] * (n - 2) + ["cta"] if n >= 3 else ["hook", "body"][:n]


async def label_sections(lines: list[str]) -> list[str]:
    numbered = "\n".join(f"{i}. {line}" for i, line in enumerate(lines))
    prompt = (
        "Label each line of this short-form video script with its section: hook (grabs attention, usually the "
        "first line or two), intro (sets up the topic), body (main content), or cta (call to action, usually last). "
        f"Return exactly {len(lines)} labels in order.\n\n{numbered}"
    )
    try:
        res = await llm.generate_json(prompt, Sections)
        if len(res.sections) == len(lines):
            return res.sections
        log.warning("Gemini returned %d section labels for %d lines, using fallback", len(res.sections), len(lines))
    except Exception:
        log.warning("Section labelling failed, using fallback", exc_info=True)
    return fallback_sections(len(lines))


async def ensure_tone_profile(user: dict, refresh: bool = False) -> str:
    """F2 tone personalization: summarize the creator's last 3 scripts into users.tone_profile (cached)."""
    if user.get("tone_profile") and not refresh:
        return user["tone_profile"]
    scripts = await db.scripts.find({"user_id": user["_id"], "source": "user"}, {"content": 1}) \
        .sort("created_at", -1).limit(3).to_list(3)
    if not scripts:
        return ""
    tone = (await llm.tone_summary([s["content"] for s in scripts])).tone.strip()
    await db.users.update_one({"_id": user["_id"]}, {"$set": {"tone_profile": tone}})
    user["tone_profile"] = tone
    return tone
