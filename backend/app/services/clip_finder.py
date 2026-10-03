"""F4: Gemini picks 15-60s self-contained moments; post-processing makes the cuts clean.

The LLM sees one sentence per line as "[MM:SS-MM:SS] text" and copies times back as
strings (no arithmetic). snap() maps those back to exact sentence/word boundaries.
"""

import logging
import math
import re
import wave
from pathlib import Path

import numpy as np
from pydantic import BaseModel

from app.services import llm

log = logging.getLogger("uvicorn.error")

MIN_S, MAX_S = 15, 60
PAD_S = 0.15
CHUNK_S, OVERLAP_S = 600, 60      # long footage goes to the LLM in 10-min windows
ENERGY_WINDOW_S = 0.5
ENERGY_MAX_BOOST = 1.0            # added to overall (1-10) for clips full of loud moments
MAX_ZOOMS_PER_CLIP = 2


class Candidate(BaseModel):
    start: str
    end: str
    title: str
    reason: str
    hook: int
    completeness: int
    virality: int
    overall: int


class Candidates(BaseModel):
    clips: list[Candidate]


class ClipEmphasis(BaseModel):
    clip: int
    words: list[str]
    sentences: list[int]


class Emphasis(BaseModel):
    clips: list[ClipEmphasis]


PROMPT = """You are a short-form video editor for a {niche} creator.{tone}
Below is a timestamped transcript of raw footage, one sentence per line: [MM:SS-MM:SS] text.
Lines marked (ad-lib) were not in the script; unscripted stories are often the best material.

Find the 3-5 best moments to post as standalone vertical clips of {min_s}-{max_s} seconds.
Rules:
- The clip must make sense with no other context.
- Start on a strong line. If the moment is great but its first line is weak, still pick it and say in the reason that it needs a hook overlay.
- End on a resolution, payoff or punchline, never mid-thought.
- Prefer stories, strong opinions, surprising facts and actionable tips.
- start = the first time of the clip's first line, end = the second time of its last line, as "MM:SS" copied exactly from the transcript.
- Clips must not overlap.
- Score each 1-10: hook (do the first 3 seconds stop the scroll), completeness (self-contained), virality (would people share it), overall.
- title: under 8 words. reason: one sentence on why it works.

Transcript:
{transcript}"""


def fmt(t: float, up: bool = False) -> str:
    s = math.ceil(t) if up else math.floor(t)
    return f"{s // 60:02d}:{s % 60:02d}"


_TS = re.compile(r"(?:(\d+):)?(\d+):(\d+(?:\.\d+)?)")


def parse_ts(s: str, last: bool = False) -> float | None:
    """'03:12', '1:03:12', or a whole copied line bracket '[03:12-03:20]' (first time, or last if `last`)."""
    found = _TS.findall(s)
    if not found:
        return None
    h, mm, ss = found[-1] if last else found[0]
    return int(h or 0) * 3600 + int(mm) * 60 + float(ss)


def transcript_lines(sents: list[dict], adlibs: list[dict]) -> str:
    out = []
    for s in sents:
        tag = " (ad-lib)" if any(a["start"] <= s["start"] < a["end"] for a in adlibs) else ""
        out.append(f"[{fmt(s['start'])}-{fmt(s['end'], up=True)}]{tag} {s['text']}")
    return "\n".join(out)


def snap(start_t: float, end_t: float, sents: list[dict]) -> tuple[int, int]:
    """LLM times (copied, whole seconds) -> first/last sentence index. Ends extend to the sentence end."""
    i0 = min(range(len(sents)), key=lambda i: (abs(math.floor(sents[i]["start"]) - start_t), i))
    i1 = min(range(i0, len(sents)), key=lambda i: (abs(math.ceil(sents[i]["end"]) - end_t), -i))
    return i0, i1


def shape(i0: int, i1: int, sents: list[dict], words: list[dict], duration: float | None) -> tuple[float, float] | None:
    """Enforce MIN_S..MAX_S: drop trailing sentences if long; if short, grow by whole sentences (forward first,
    which completes the thought) so a good-but-short pick from a weaker model isn't thrown away.
    Then pad PAD_S without touching neighbour words."""
    while i1 > i0 and sents[i1]["end"] - sents[i0]["start"] > MAX_S:
        i1 -= 1
    while sents[i1]["end"] - sents[i0]["start"] < MIN_S:
        if i1 + 1 < len(sents) and sents[i1 + 1]["end"] - sents[i0]["start"] <= MAX_S:
            i1 += 1
        elif i0 > 0 and sents[i1]["end"] - sents[i0 - 1]["start"] <= MAX_S:
            i0 -= 1
        else:
            break
    if not MIN_S <= sents[i1]["end"] - sents[i0]["start"] <= MAX_S:
        return None
    w0, w1 = sents[i0]["w0"], sents[i1]["w1"]
    start = max(sents[i0]["start"] - PAD_S, words[w0 - 1]["end"] if w0 > 0 else 0.0)
    limit = words[w1 + 1]["start"] if w1 + 1 < len(words) else (duration or math.inf)
    end = min(sents[i1]["end"] + PAD_S, limit)
    return round(start, 3), round(end, 3)


def remove_overlaps(clips: list[dict], taken: list[tuple[float, float]] = ()) -> list[dict]:
    """Highest overall score wins; `taken` are ranges of clips we must not overlap (e.g. user-approved)."""
    kept, ranges = [], list(taken)
    for c in sorted(clips, key=lambda c: c["scores"]["overall"], reverse=True):
        if all(c["end"] <= s or c["start"] >= e for s, e in ranges):
            kept.append(c)
            ranges.append((c["start"], c["end"]))
    return kept


def energy_boosts(audio: Path, ranges: list[tuple[float, float]]) -> list[float]:
    """Share of each range that sits in the loudest 10% of the footage (laughs, emphasis) -> 0..ENERGY_MAX_BOOST."""
    with wave.open(str(audio)) as w:
        rate = w.getframerate()
        data = np.frombuffer(w.readframes(w.getnframes()), dtype=np.int16).astype(np.float32)
    win = int(rate * ENERGY_WINDOW_S)
    n = len(data) // win
    if n == 0:
        return [0.0] * len(ranges)
    rms = np.sqrt((data[: n * win].reshape(n, win) ** 2).mean(axis=1))
    loud = rms >= np.percentile(rms, 90)
    boosts = []
    for s, e in ranges:
        part = loud[int(s / ENERGY_WINDOW_S): int(e / ENERGY_WINDOW_S) + 1]
        boosts.append(round(min(ENERGY_MAX_BOOST, float(part.mean()) * 3 * ENERGY_MAX_BOOST), 2) if len(part) else 0.0)
    return boosts


async def find_clips(
    sents: list[dict],
    words: list[dict],
    duration: float | None,
    audio: Path | None = None,
    niche: str = "",
    tone: str = "",
    adlibs: list[dict] = (),
    taken: list[tuple[float, float]] = (),
) -> list[dict]:
    """Returns [{start, end, title, reason, scores}] sorted by overall score, padded and non-overlapping."""
    if not sents:
        return []
    raw: list[Candidate] = []
    t0, last_start = 0.0, sents[-1]["start"]
    while t0 <= last_start:
        chunk = [s for s in sents if t0 <= s["start"] < t0 + CHUNK_S]
        if chunk:
            prompt = PROMPT.format(
                niche=niche or "general", tone=f"\nCreator tone: {tone}" if tone else "",
                min_s=MIN_S, max_s=MAX_S, transcript=transcript_lines(chunk, list(adlibs)),
            )
            raw += (await llm.generate_json(prompt, Candidates, deep=True)).clips
        t0 += CHUNK_S - OVERLAP_S

    clips = []
    for c in raw:
        start_t, end_t = parse_ts(c.start), parse_ts(c.end, last=True)
        if start_t is None or end_t is None or end_t <= start_t:
            log.info("Dropping clip %r: unparseable times %r-%r", c.title, c.start, c.end)
            continue
        shaped = shape(*snap(start_t, end_t, sents), sents, words, duration)
        if not shaped:
            log.info("Dropping clip %r: outside %s-%ss", c.title, MIN_S, MAX_S)
            continue
        clamp = lambda x: float(min(10, max(1, x)))  # noqa: E731
        clips.append({
            "start": shaped[0], "end": shaped[1], "title": c.title.strip(), "reason": c.reason.strip(),
            "scores": {"hook": clamp(c.hook), "completeness": clamp(c.completeness),
                       "virality": clamp(c.virality), "overall": clamp(c.overall)},
        })

    if audio and clips:
        for c, boost in zip(clips, energy_boosts(audio, [(c["start"], c["end"]) for c in clips])):
            c["scores"]["overall"] = round(min(10.0, c["scores"]["overall"] + boost), 2)
    return remove_overlaps(clips, taken)


async def pick_emphasis(clips: list[dict], sents: list[dict]) -> list[tuple[set[str], list[tuple[float, float]]]]:
    """One LLM call for all clips: caption emphasis words + sentences that get a zoom punch.
    Returns per clip (emphasis_words, [(sentence_start, sentence_end)]). Failure -> no emphasis.
    """
    blocks = [[s for s in sents if s["start"] >= c["start"] - 0.01 and s["end"] <= c["end"] + 0.01] for c in clips]
    text = "\n\n".join(
        f"Clip {k}:\n" + "\n".join(f"  {j}. {s['text']}" for j, s in enumerate(b)) for k, b in enumerate(blocks)
    )
    prompt = ("For each short-form clip below, pick 1-4 words worth emphasizing in on-screen captions (copy exact "
              "words from the text: numbers, strong verbs, the surprising word), and 0-2 sentence numbers that deserve "
              f"a zoom punch-in (the punchline or most surprising line).\n\n{text}")
    try:
        by_clip = {e.clip: e for e in (await llm.generate_json(prompt, Emphasis)).clips}
    except Exception:
        log.warning("Emphasis picking failed; clips get plain captions", exc_info=True)
        return [(set(), []) for _ in clips]
    out = []
    for k, b in enumerate(blocks):
        e = by_clip.get(k)
        zooms = [(b[j]["start"], b[j]["end"]) for j in (e.sentences if e else []) if 0 <= j < len(b)]
        out.append((set(e.words) if e else set(), zooms[:MAX_ZOOMS_PER_CLIP]))
    return out
