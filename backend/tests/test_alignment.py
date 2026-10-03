import asyncio
import os
from collections import Counter

os.environ.setdefault("JWT_SECRET", "test-secret-at-least-32-bytes-long!!")

from app.services.alignment import (  # noqa: E402
    Window, _best, align, attach_visuals, normalize, rough_cut_edl,
)

SCRIPT = [
    "Most people think saving money is about cutting coffee.",
    "Last year I lost 50,000 rupees on a stock tip.",
    "Here is the one rule I follow now.",
    "Never invest in something you cannot explain in one sentence.",  # never spoken -> missing
    "Follow for more money lessons every week.",
]

SPOKEN = [
    "Most people think saving money is about cutting coffee.",
    "Last year I lost 50,000 rupees on a, uh, on a stock",               # stumbled first take
    "Last year I lost 50,000 rupees on a stock tip.",                    # clean retake
    "Honestly my dad still laughs about that whole story at dinner.",    # ad-lib
    "Here is the one rule I follow now.",
    "Follow for more money lessons every week.",
]


def make_segments(sentences, word_s=0.3, gap_s=1.0):
    segs, t = [], 0.0
    for idx, sentence in enumerate(sentences):
        words = []
        for w in sentence.split():
            words.append({"w": w, "start": round(t, 3), "end": round(t + word_s - 0.05, 3), "conf": 0.9})
            t += word_s
        segs.append({"idx": idx, "start": words[0]["start"], "end": words[-1]["end"], "text": sentence, "words": words})
        t += gap_s
    return segs


async def fake_embed(texts):
    """Bag-of-words vectors: identical text -> cosine 1, unrelated -> ~0 (stands in for Gemini)."""
    vocab = sorted({t for text in texts for t in normalize(text).split()})
    return [[Counter(normalize(text).split())[v] for v in vocab] for text in texts]


def run_align():
    lines = [{"idx": i, "text": t} for i, t in enumerate(SCRIPT)]
    return asyncio.run(align(lines, make_segments(SPOKEN), fake_embed))


def test_normalize():
    assert normalize("I lost ₹50,000 (that's 12.5%)!") == "i lost rupees fifty thousand thats twelve point five percent"
    assert normalize("1,234") == "one thousand two hundred thirty four"


def test_retake_picks_clean_later_take():
    m = run_align()["matches"][1]
    assert m["status"] == "matched"
    assert len(m["takes"]) == 2, m["takes"]                       # both attempts found
    assert m["best_take_index"] == 1                               # the clean retake
    assert m["takes"][1]["transcript_segment_idxs"] == [2]
    assert m["takes"][1]["similarity"] > m["takes"][0]["similarity"]


def test_missing_line_and_coverage():
    a = run_align()
    statuses = [m["status"] for m in a["matches"]]
    assert statuses == ["matched", "matched", "matched", "missing", "matched"]
    assert a["matches"][3]["takes"] == [] and a["matches"][3]["best_take_index"] is None
    assert a["coverage"] == 0.8


def test_adlib_is_unscripted():
    ranges = run_align()["unscripted_ranges"]
    assert len(ranges) == 1
    assert ranges[0]["text"].startswith("Honestly my dad")
    assert "dinner" in ranges[0]["text"]


def test_best_takes_follow_script_order():
    a = run_align()
    starts = [m["takes"][m["best_take_index"]]["start"] for m in a["matches"] if m["takes"]]
    assert starts == sorted(starts)


def test_out_of_order_weak_match_dropped():
    # line 0 is only spoken (sloppily) at the very end, after line 1 -> breaks order, too weak to keep
    lines = [{"idx": 0, "text": "Cutting coffee will not make you rich"},
             {"idx": 1, "text": "Here is the one rule I follow now."}]
    segs = make_segments(["Here is the one rule I follow now.", "cutting coffee will never make anyone rich"])
    a = asyncio.run(align(lines, segs, fake_embed))
    assert [m["status"] for m in a["matches"]] == ["missing", "matched"]


def test_short_line_no_false_retakes():
    # "One tip." must not match every lone "one" in the footage
    lines = [{"idx": 0, "text": "One tip."}]
    segs = make_segments(["I had one idea.", "One tip.", "Only one thing matters."])
    m = asyncio.run(align(lines, segs, fake_embed))["matches"][0]
    assert len(m["takes"]) == 1 and m["takes"][0]["transcript_segment_idxs"] == [1]


def test_tie_break_prefers_clean_then_later():
    w = lambda a, sim, pen: Window(a, a + 5, 1.0, 1.0, sim, pen)
    assert _best([w(0, 0.95, 0), w(10, 0.94, 2)]) == 0            # tie -> fewer fillers wins over later
    assert _best([w(0, 0.95, 1), w(10, 0.94, 1)]) == 1            # tie, equal penalty -> later take
    assert _best([w(0, 0.99, 3), w(10, 0.80, 0)]) == 0            # not a tie -> similarity wins


def test_visuals_and_rough_cut():
    a = run_align()
    attach_visuals(a, [{"t": 0.0, "description": "speaker at desk"}, {"t": 30.0, "description": "close-up on phone"}])
    assert a["matches"][0]["takes"][0]["visual"] == "speaker at desk"
    edl = rough_cut_edl(a)
    best = [m["takes"][m["best_take_index"]] for m in a["matches"] if m["takes"]]
    assert edl["segments"] == [{"start": t["start"], "end": t["end"]} for t in best]
    assert len(edl["segments"]) == 4 and edl["aspect_ratio"] == "16:9"

