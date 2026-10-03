import os
import random
from datetime import datetime, timezone
from statistics import mean

os.environ.setdefault("JWT_SECRET", "test-secret-at-least-32-bytes-long!!")

from app.services.insights import MOCK_HOOKS, mock_post  # noqa: E402
from app.services.search import best_sentence, chunk_transcript  # noqa: E402


def words_for(sentences, start=0.0, word_s=0.5):
    out, t = [], start
    for s in sentences:
        for w in s.split():
            out.append({"w": w, "start": t, "end": t + word_s - 0.05})
            t += word_s
    return out


def test_chunks_are_about_30s_on_sentence_boundaries():
    words = words_for([f"Sentence number {i} has exactly seven words." for i in range(30)])  # 3.5s each, 105s total
    chunks = chunk_transcript(words)
    assert all(c["text"].endswith(".") for c in chunks)
    assert all(30 <= c["end"] - c["start"] + 0.05 <= 34 for c in chunks[:-1])
    assert chunks[0]["start"] == 0 and abs(chunks[-1]["end"] - words[-1]["end"]) < 1e-9


def test_best_sentence_targets_the_matching_line():
    words = words_for(["We talked about rent first.", "Then my dad laughed at the stock tip.", "Follow for more."])
    line = best_sentence("dad laughing at my stock tip", words, 0, 100)
    assert line["text"] == "Then my dad laughed at the stock tip." and line["start"] == 2.5
    assert best_sentence("quantum physics", words, 0, 100) is None   # no lexical match -> caller keeps chunk start


def test_mock_posts_favour_question_hooks():
    rng = random.Random(7)
    at = datetime(2026, 9, 1, 14, tzinfo=timezone.utc)
    ret = {h: mean(mock_post(rng, "shorts", h, at, "t")["metrics"]["retention_3s"] for _ in range(200)) for h in MOCK_HOOKS}
    assert max(ret, key=ret.get) == "question" and min(ret, key=ret.get) == "statistic"
    post = mock_post(rng, "linkedin", "story", at, "Title")
    assert post["mock"] is True and post["metrics"]["views"] > 0 and post["metrics"]["likes"] < post["metrics"]["views"]
