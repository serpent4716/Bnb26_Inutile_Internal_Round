"""F5: build Edit Decision Lists. Every cut lands on a word timestamp, never mid-word.

Segment times are source-video seconds; captions and zooms are output-timeline seconds
(0 = first frame of the edited clip), as in ARCHITECTURE.md.
"""

import re

from app.models.clip import EDL
from app.services.transcription import filler_mask

MAX_GAP_S = 0.5      # silence longer than this between kept words gets cut
EDGE_PAD_S = 0.08    # breathing room kept around each cut, so jump cuts don't clip consonants
ZOOM_SCALE = 1.2     # F5: 1.15-1.25x punch-in on emphasized sentences
CAPTION_MAX_WORDS = 3
_PUNCT_END = re.compile(r"[.!?,;:][\"')\]]*$")


def clip_word_range(words: list[dict], start: float, end: float) -> list[int]:
    return [i for i, w in enumerate(words) if w["start"] >= start - 0.01 and w["end"] <= end + 0.01]


def retake_words(words: list[dict], alignment: dict | None) -> set[int]:
    """Words inside a non-best take of any script line (the flubbed attempts)."""
    if not alignment:
        return set()
    drop: set[int] = set()
    for m in alignment["matches"]:
        if len(m["takes"]) < 2:
            continue
        best = m["takes"][m["best_take_index"]]
        for k, take in enumerate(m["takes"]):
            if k == m["best_take_index"]:
                continue
            drop.update(i for i, w in enumerate(words)
                        if w["start"] >= take["start"] - 0.01 and w["end"] <= take["end"] + 0.01
                        and not (w["start"] >= best["start"] and w["end"] <= best["end"]))
    return drop


def kept_words(words: list[dict], idxs: list[int], drop: set[int]) -> list[int]:
    """Clip words minus fillers and retakes."""
    fillers = filler_mask([words[i]["w"] for i in idxs])
    return [i for i, f in zip(idxs, fillers) if not f and i not in drop]


def to_segments(words: list[dict], kept: list[int], clip_idxs: list[int], clip_start: float, clip_end: float) -> list[dict]:
    """Group kept words into source segments. A new segment starts after a removed word or a gap > MAX_GAP_S.
    The clip finder's outer padding (clip_start/clip_end) applies only where the edge word was kept.
    """
    groups: list[list[int]] = []
    for i in kept:
        if groups and i == groups[-1][-1] + 1 and words[i]["start"] - words[i - 1]["end"] <= MAX_GAP_S:
            groups[-1].append(i)
        else:
            groups.append([i])

    segs = []
    for g in groups:
        a, b = g[0], g[-1]
        before = words[a]["start"] - words[a - 1]["end"] if a > 0 else EDGE_PAD_S * 2
        after = words[b + 1]["start"] - words[b]["end"] if b + 1 < len(words) else EDGE_PAD_S * 2
        segs.append({
            "start": round(max(0.0, words[a]["start"] - min(EDGE_PAD_S, max(before, 0) / 2)), 3),
            "end": round(words[b]["end"] + min(EDGE_PAD_S, max(after, 0) / 2), 3),
        })
    if segs and kept[0] == clip_idxs[0]:
        segs[0]["start"] = round(min(segs[0]["start"], clip_start), 3)
    if segs and kept[-1] == clip_idxs[-1]:
        segs[-1]["end"] = round(max(segs[-1]["end"], clip_end), 3)
    return segs


def output_time(t: float, segs: list[dict]) -> float:
    """Source time -> clip timeline time (time inside a cut maps to the cut point)."""
    offset = 0.0
    for s in segs:
        if t < s["start"]:
            return round(offset, 3)
        if t <= s["end"]:
            return round(offset + t - s["start"], 3)
        offset += s["end"] - s["start"]
    return round(offset, 3)


def build_captions(words: list[dict], kept: list[int], segs: list[dict], emphasis: set[str]) -> list[dict]:
    """2-4 word chunks, breaking after punctuation; chunks containing an emphasis word get style "emphasis"."""
    chunks: list[list[int]] = []
    cur: list[int] = []
    for i in kept:
        cur.append(i)
        if len(cur) == CAPTION_MAX_WORDS or (len(cur) >= 2 and _PUNCT_END.search(words[i]["w"])):
            chunks.append(cur)
            cur = []
    if cur:
        if len(cur) == 1 and chunks:
            chunks[-1] += cur  # no orphan single word; max becomes 4
        else:
            chunks.append(cur)

    def norm(w: str) -> str:
        return re.sub(r"[^\w']", "", w.lower())

    emph = {norm(e) for e in emphasis}
    return [{
        "start": output_time(words[c[0]]["start"], segs),
        "end": output_time(words[c[-1]]["end"], segs),
        "text": " ".join(words[i]["w"] for i in c),
        "style": "emphasis" if any(norm(words[i]["w"]) in emph for i in c) else "bold",
    } for c in chunks]


def build_zooms(sentence_ranges: list[tuple[float, float]], segs: list[dict]) -> list[dict]:
    zooms = []
    for s, e in sentence_ranges:
        start, end = output_time(s, segs), output_time(e, segs)
        if end > start:
            zooms.append({"start": start, "end": end, "scale": ZOOM_SCALE})
    return zooms


def build_edl(
    words: list[dict],
    start: float,
    end: float,
    alignment: dict | None = None,
    emphasis_words: set[str] = frozenset(),
    zoom_sentences: list[tuple[float, float]] = (),
    aspect_ratio: str = "9:16",
) -> dict:
    """Initial AI EDL for a clip range: retakes, fillers and long silences cut; captions; zoom punches.
    Validated against the EDL model (DATABASE_SCHEMA.md clips.edl).
    """
    idxs = clip_word_range(words, start, end)
    kept = kept_words(words, idxs, retake_words(words, alignment))
    segs = to_segments(words, kept, idxs, start, end)
    edl = {
        "aspect_ratio": aspect_ratio,
        "segments": segs,
        "captions": build_captions(words, kept, segs, emphasis_words),
        "zooms": build_zooms(list(zoom_sentences), segs),
        "crop_track": [],  # F6 smart reframe fills this
        "overlays": [],
    }
    return EDL.model_validate(edl).model_dump()


def edl_duration(edl: dict) -> float:
    return round(sum(s["end"] - s["start"] for s in edl["segments"]), 3)


def trim(edl: dict, max_dur: float | None, words: list[dict]) -> dict:
    """Shorten to max_dur by dropping trailing segments; a segment that straddles the limit is cut
    at the last word that fits (never mid-word). Captions/zooms/overlays/crop_track are clipped to match."""
    if not max_dur or edl_duration(edl) <= max_dur:
        return edl
    segs, total = [], 0.0
    for s in edl["segments"]:
        room = max_dur - total
        if s["end"] - s["start"] <= room:
            segs.append(s)
            total += s["end"] - s["start"]
            continue
        fits = [w["end"] for w in words if w["start"] >= s["start"] and w["end"] <= s["start"] + room]
        if fits:
            segs.append({"start": s["start"], "end": max(fits)})
        break
    total = sum(s["end"] - s["start"] for s in segs)

    def clip(items):
        return [dict(i, end=min(i["end"], total)) for i in items if i["start"] < total]

    return {**edl, "segments": segs, "captions": clip(edl["captions"]), "zooms": clip(edl["zooms"]),
            "overlays": clip(edl["overlays"]), "crop_track": [p for p in edl["crop_track"] if p["t"] <= total]}


def platform_variant(edl: dict, preset: dict, words: list[dict]) -> dict:
    """F6: the clip's EDL adapted to a PLATFORMS preset (aspect, captions on/off + style, max length)."""
    out = {
        **edl,
        "aspect_ratio": preset["aspect"],
        "captions": edl["captions"] if preset["captions"] else [],
        "caption_style": preset.get("caption_style", "bold_center"),
    }
    return EDL.model_validate(trim(out, preset["max_dur"], words)).model_dump()


def with_hook(edl: dict, text: str, seconds: float = 2.0) -> dict:
    """Replace the hook overlay: `text` on screen for the first `seconds` of the clip."""
    others = [o for o in edl["overlays"] if o["type"] != "hook"]
    hook = {"type": "hook", "asset_id": None, "text": text, "start": 0.0, "end": min(seconds, edl_duration(edl))}
    return {**edl, "overlays": [hook, *others]}
