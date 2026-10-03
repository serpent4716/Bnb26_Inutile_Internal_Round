"""F3: script lines <-> transcript alignment. Finds every take of each line (retakes),
picks the best one, enforces script order, flags missing lines and unscripted ad-libs.
"""

import math
import re
from dataclasses import dataclass
from typing import Awaitable, Callable

from rapidfuzz import fuzz

from app.services.transcription import is_filler_word

Embed = Callable[[list[str]], Awaitable[list[list[float]]]]

TAKE_THRESHOLD = 0.75
LEXICAL_WEIGHT, SEMANTIC_WEIGHT = 0.6, 0.4
# Calibration knob: gemini-embedding-001 scores unrelated sentences ~0.7 cosine,
# so rescale [COS_FLOOR, 1] -> [0, 1] or the semantic term can't tell junk from a match.
COS_FLOOR = 0.7
WINDOW_SLACK = 0.3       # window length = line length +-30%
LEXICAL_FLOOR = 0.5      # windows below this can't reach the threshold; don't embed them
# token_set_ratio scores any subset of the line 1.0 ("one" vs "one tip"), so a take must
# also contain this share of the line's distinct words. Matters most for short lines.
MIN_LINE_COVERAGE = 0.75
MAX_CANDIDATES = 6       # per line, after non-overlap suppression
TIE_EPS = 0.03           # takes this close in similarity count as tied
OUT_OF_ORDER_MIN = 0.9   # a take may break script order only above this
MIN_ADLIB_WORDS = 4      # non-filler words for an uncovered stretch to count as an ad-lib

# ---------- normalization ----------

_ONES = ("zero one two three four five six seven eight nine ten eleven twelve thirteen fourteen "
         "fifteen sixteen seventeen eighteen nineteen").split()
_TENS = "_ _ twenty thirty forty fifty sixty seventy eighty ninety".split()
_SCALES = ((10**9, "billion"), (10**6, "million"), (1000, "thousand"), (100, "hundred"))
_SYMBOLS = {"%": " percent ", "₹": " rupees ", "$": " dollars ", "&": " and "}


def num_to_words(n: int) -> str:
    if n < 20:
        return _ONES[n]
    if n < 100:
        return _TENS[n // 10] + (f" {_ONES[n % 10]}" if n % 10 else "")
    for value, name in _SCALES:
        if n >= value:
            head, rest = divmod(n, value)
            return f"{num_to_words(head)} {name}" + (f" {num_to_words(rest)}" if rest else "")
    raise AssertionError  # unreachable


def _number(match: re.Match) -> str:
    whole, _, frac = match.group().partition(".")
    words = num_to_words(int(whole))
    return f" {words} point {' '.join(_ONES[int(d)] for d in frac)} " if frac else f" {words} "


def normalize(text: str) -> str:
    """Lowercase, numbers to words, symbols to words, strip punctuation."""
    text = text.lower()
    for sym, word in _SYMBOLS.items():
        text = text.replace(sym, word)
    text = re.sub(r"(?<=\d),(?=\d)", "", text)          # 50,000 -> 50000
    text = re.sub(r"\d+(?:\.\d+)?", _number, text)
    text = text.replace("'", "").replace("’", "")         # don't -> dont
    return " ".join(re.findall(r"[^\W_]+", text))


# ---------- matching ----------

@dataclass
class Window:
    a: int            # token range [a, b)
    b: int
    lexical: float
    tight: float      # order/length-sensitive score, used only to choose boundaries
    similarity: float = 0.0
    penalty: int = 0  # fillers + stutters inside the take


def _candidates(line_toks: list[str], toks: list[str]) -> list[Window]:
    """Lexical sliding window; windows must start and end on a word from the line (tight boundaries)."""
    n, vocab, line = len(line_toks), set(line_toks), " ".join(line_toks)
    lo, hi = max(1, round(n * (1 - WINDOW_SLACK))), max(1, round(n * (1 + WINDOW_SLACK)))
    wins = []
    for a, tok in enumerate(toks):
        if tok not in vocab:
            continue
        for b in range(a + lo, min(a + hi, len(toks)) + 1):
            if toks[b - 1] not in vocab or len(vocab.intersection(toks[a:b])) < MIN_LINE_COVERAGE * len(vocab):
                continue
            text = " ".join(toks[a:b])
            lex = fuzz.token_set_ratio(line, text) / 100
            if lex >= LEXICAL_FLOOR:
                wins.append(Window(a, b, lex, fuzz.ratio(line, text) / 100))
    # Non-overlap suppression: best window per region. token_set_ratio alone scores sub/super-windows 1.0,
    # so rank by the average with the length-sensitive ratio to land on the real boundaries.
    wins.sort(key=lambda w: w.lexical + w.tight, reverse=True)
    picked: list[Window] = []
    for w in wins:
        if all(w.b <= p.a or w.a >= p.b for p in picked):
            picked.append(w)
            if len(picked) == MAX_CANDIDATES:
                break
    return picked


def _cos(u: list[float], v: list[float]) -> float:
    dot = sum(x * y for x, y in zip(u, v))
    norm = math.sqrt(sum(x * x for x in u)) * math.sqrt(sum(y * y for y in v))
    return dot / norm if norm else 0.0


def _best(takes: list[Window]) -> int:
    """Highest similarity; near-ties go to fewer fillers/stutters, then the later take."""
    top = max(t.similarity for t in takes)
    tied = [i for i, t in enumerate(takes) if t.similarity >= top - TIE_EPS]
    return min(tied, key=lambda i: (takes[i].penalty, -takes[i].a))


def _in_order_chain(starts: dict[int, int], sims: dict[int, float]) -> set[int]:
    """Weighted longest increasing subsequence over lines: max total similarity with non-decreasing start."""
    lines = sorted(starts)
    score, prev = {}, {}
    for k, i in enumerate(lines):
        score[i], prev[i] = sims[i], None
        for j in lines[:k]:
            if starts[j] <= starts[i] and score[j] + sims[i] > score[i]:
                score[i], prev[i] = score[j] + sims[i], j
    chain, i = set(), max(score, key=score.get) if score else None
    while i is not None:
        chain.add(i)
        i = prev[i]
    return chain


async def align(lines: list[dict], segments: list[dict], embed: Embed) -> dict:
    """Script `lines` [{idx, text}] x transcript `segments` -> alignment body
    {matches, unscripted_ranges, coverage} per DATABASE_SCHEMA.md.
    """
    words, seg_of = [], []
    for s in segments:
        for w in s["words"]:
            words.append(w)
            seg_of.append(s["idx"])
    toks, owner = [], []  # normalized tokens, and the word each came from
    for i, w in enumerate(words):
        for t in normalize(w["w"]).split():
            toks.append(t)
            owner.append(i)

    cands = [_candidates(normalize(line["text"]).split(), toks) for line in lines]

    # Semantic half of the score, embedding only lexical survivors in one batch.
    def span_text(w: Window) -> str:
        return " ".join(words[k]["w"] for k in range(owner[w.a], owner[w.b - 1] + 1))

    flat = [(i, w) for i, c in enumerate(cands) for w in c]
    if flat:
        vecs = await embed([line["text"] for line in lines] + [span_text(w) for _, w in flat])
        for (i, w), vec in zip(flat, vecs[len(lines):]):
            sem = max(0.0, (_cos(vecs[i], vec) - COS_FLOOR) / (1 - COS_FLOOR))
            w.similarity = round(LEXICAL_WEIGHT * w.lexical + SEMANTIC_WEIGHT * min(sem, 1.0), 3)
            stutters = sum(toks[k] == toks[k + 1] for k in range(w.a, w.b - 1))
            fillers = sum(is_filler_word(words[k]["w"]) for k in range(owner[w.a], owner[w.b - 1] + 1))
            w.penalty = stutters + fillers

    takes = [sorted((w for w in c if w.similarity >= TAKE_THRESHOLD), key=lambda w: w.a) for c in cands]
    best = {i: _best(t) for i, t in enumerate(takes) if t}

    # Enforce script order; off-chain lines keep a take only if it fits between neighbours or is very strong.
    chain = _in_order_chain({i: takes[i][b].a for i, b in best.items()}, {i: takes[i][b].similarity for i, b in best.items()})
    for i in sorted(set(best) - chain):
        if takes[i][best[i]].similarity >= OUT_OF_ORDER_MIN:
            continue
        before = [takes[j][best[j]].a for j in chain if j < i]
        after = [takes[j][best[j]].a for j in chain if j > i]
        lo, hi = max(before, default=-1), min(after, default=len(toks))
        takes[i] = [t for t in takes[i] if lo <= t.a <= hi]
        if takes[i]:
            best[i] = _best(takes[i])
        else:
            del best[i]

    matches, covered = [], set()
    for i, line in enumerate(lines):
        out = []
        for w in takes[i] if i in best else []:
            w0, w1 = owner[w.a], owner[w.b - 1]
            covered.update(range(w0, w1 + 1))
            out.append({
                "start": words[w0]["start"],
                "end": words[w1]["end"],
                "similarity": w.similarity,
                "transcript_segment_idxs": sorted(set(seg_of[w0:w1 + 1])),
            })
        matches.append({
            "script_line_idx": line["idx"],
            "takes": out,
            "best_take_index": best.get(i),
            "status": "matched" if out else "missing",
        })

    unscripted, run = [], []
    for k in range(len(words) + 1):
        if k < len(words) and k not in covered:
            run.append(k)
            continue
        if sum(not is_filler_word(words[j]["w"]) for j in run) >= MIN_ADLIB_WORDS:
            unscripted.append({
                "start": words[run[0]]["start"],
                "end": words[run[-1]]["end"],
                "text": " ".join(words[j]["w"] for j in run),
            })
        run = []

    matched = sum(m["status"] == "matched" for m in matches)
    return {"matches": matches, "unscripted_ranges": unscripted, "coverage": round(matched / len(lines), 3) if lines else 0.0}


def attach_visuals(alignment: dict, keyframes: list[dict]) -> None:
    """Give each take the description of the keyframe nearest its midpoint (in place)."""
    if not keyframes:
        return
    for m in alignment["matches"]:
        for take in m["takes"]:
            mid = (take["start"] + take["end"]) / 2
            take["visual"] = min(keyframes, key=lambda k: abs(k["t"] - mid))["description"]


def rough_cut_edl(alignment: dict) -> dict:
    """Best takes concatenated in script order -> full-video EDL (word-boundary cuts)."""
    segments = [
        {"start": t["start"], "end": t["end"]}
        for m in sorted(alignment["matches"], key=lambda m: m["script_line_idx"])
        if m["takes"]
        for t in [m["takes"][m["best_take_index"]]]
        if t["end"] > t["start"]
    ]
    return {"aspect_ratio": "16:9", "segments": segments, "captions": [], "zooms": [], "crop_track": [], "overlays": []}
