import os
import wave
from array import array

os.environ.setdefault("JWT_SECRET", "test-secret-at-least-32-bytes-long!!")

import pytest  # noqa: E402

from app.models.clip import EDL  # noqa: E402
from app.services.clip_finder import energy_boosts, parse_ts, remove_overlaps, shape, snap  # noqa: E402
from app.services.edl import build_edl, output_time  # noqa: E402
from app.services.transcription import sentences  # noqa: E402


def words_from(spec):
    """spec: list of (word, start, end)."""
    return [{"w": w, "start": s, "end": e, "conf": None} for w, s, e in spec]


# "So, um, I lost money. [1.2s pause] Then I, you know, learned. [retake] Here is the rule. Here is the rule!"
WORDS = words_from([
    ("So,", 0.0, 0.3), ("um,", 0.4, 0.6), ("I", 0.7, 0.8), ("lost", 0.85, 1.1), ("money.", 1.15, 1.6),
    ("Then", 2.8, 3.0), ("I,", 3.05, 3.2), ("you", 3.3, 3.4), ("know,", 3.45, 3.7), ("learned.", 3.75, 4.3),
    ("Here", 5.0, 5.2), ("is", 5.25, 5.35), ("the", 5.4, 5.5), ("rule.", 5.55, 5.9),        # flubbed take
    ("Here", 7.0, 7.2), ("is", 7.25, 7.35), ("the", 7.4, 7.5), ("rule!", 7.55, 8.0),        # best take
])
ALIGNMENT = {"matches": [{"script_line_idx": 0, "best_take_index": 1, "status": "matched",
                          "takes": [{"start": 5.0, "end": 5.9}, {"start": 7.0, "end": 8.0}]}]}


def test_sentences_split_on_punctuation_and_pauses():
    s = sentences(WORDS)
    assert [x["text"] for x in s] == ["So, um, I lost money.", "Then I, you know, learned.", "Here is the rule.", "Here is the rule!"]
    assert (s[1]["w0"], s[1]["w1"]) == (5, 9)


def test_edl_cuts_fillers_retakes_and_silence():
    edl = build_edl(WORDS, 0.0, 8.15, ALIGNMENT, emphasis_words={"money"}, zoom_sentences=[(7.0, 8.0)])
    EDL.model_validate(edl)
    kept_text = " ".join(c["text"] for c in edl["captions"])
    assert "um," not in kept_text and "know," not in kept_text      # fillers cut
    assert kept_text.count("Here") == 1                               # flubbed retake cut
    segs = edl["segments"]
    # every cut lands outside words: no segment boundary falls inside a kept word
    for s in segs:
        for w in WORDS:
            assert not (w["start"] < s["start"] < w["end"]) and not (w["start"] < s["end"] < w["end"])
    # silence (1.2s after "money.") and the gap to the best take are removed
    assert not any(s["start"] < 2.0 < s["end"] for s in segs)
    assert not any(s["start"] < 6.5 < s["end"] for s in segs)
    # the "um," at 0.4-0.6 is not inside any segment
    assert not any(s["start"] <= 0.45 and s["end"] >= 0.55 for s in segs)
    assert segs[-1]["end"] == 8.15                                    # clip padding kept at the edge


def test_captions_and_zooms_use_output_timeline():
    edl = build_edl(WORDS, 0.0, 8.15, ALIGNMENT, emphasis_words={"money"}, zoom_sentences=[(7.0, 8.0)])
    caps, segs = edl["captions"], edl["segments"]
    assert caps[0]["start"] == 0.0
    assert all(2 <= len(c["text"].split()) <= 4 for c in caps)
    assert all(a["end"] <= b["start"] + 1e-6 for a, b in zip(caps, caps[1:]))
    assert any(c["style"] == "emphasis" and "money" in c["text"] for c in caps)
    total = sum(s["end"] - s["start"] for s in segs)
    assert caps[-1]["end"] <= total + 1e-6
    assert edl["zooms"] == [{"start": output_time(7.0, segs), "end": output_time(8.0, segs), "scale": 1.2}]


def test_soft_fillers_need_commas():
    words = words_from([("I", 0, 0.2), ("like", 0.25, 0.5), ("this.", 0.55, 0.9)])
    assert " ".join(c["text"] for c in build_edl(words, 0, 0.9)["captions"]) == "I like this."


def test_snap_shape_pad():
    # 30 sentences of 2s each, 0.5s apart: sentence i spans [2.5i, 2.5i+2]
    ws = []
    for i in range(30):
        ws += words_from([("word", 2.5 * i, 2.5 * i + 1.0), ("end.", 2.5 * i + 1.1, 2.5 * i + 2.0)])
    sents = sentences(ws)
    assert len(sents) == 30
    assert parse_ts("00:10") == 10 and parse_ts("1:02:03") == 3723 and parse_ts("ten") is None
    # Gemini sometimes copies the whole line bracket instead of one time
    assert parse_ts("[00:27-00:31]") == 27 and parse_ts("[01:00-01:02]", last=True) == 62
    i0, i1 = snap(10, 32, sents)            # displayed [00:10-...] and [...-00:32]
    assert (sents[i0]["start"], sents[i1]["end"]) == (10.0, 32.0)
    start, end = shape(i0, i1, sents, ws, duration=75)
    assert (start, end) == (9.85, 32.15)    # 0.15s pad, gaps to neighbours are 0.5s
    assert shape(0, 3, sents, ws, 75) is None                 # 9.5s < 15s minimum
    long = shape(0, 29, sents, ws, 75)                         # 74.5s -> trimmed to <= 60s at a sentence end
    assert long and long[1] - long[0] <= 60.3 and long[1] - 0.15 in [s["end"] for s in sents]


def test_remove_overlaps_keeps_higher_score():
    mk = lambda s, e, o: {"start": s, "end": e, "scores": {"overall": o}}  # noqa: E731
    kept = remove_overlaps([mk(0, 20, 6), mk(10, 30, 9), mk(30, 50, 5), mk(55, 70, 7)], taken=[(52, 60)])
    assert [(c["start"], c["scores"]["overall"]) for c in kept] == [(10, 9), (30, 5)]


def test_energy_boost_favours_loud_range(tmp_path):
    rate, path = 16000, tmp_path / "a.wav"
    samples = [8000 if 10 <= i / rate < 12 else 200 for i in range(20 * rate)]  # loud 10-12s
    with wave.open(str(path), "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(rate)
        w.writeframes(array("h", samples).tobytes())
    quiet, loud = energy_boosts(path, [(0, 8), (9, 13)])
    assert quiet == 0 and loud > 0.5


def test_edl_rejects_backwards_segment():
    with pytest.raises(ValueError):
        EDL.model_validate({"segments": [{"start": 5, "end": 4}]})
