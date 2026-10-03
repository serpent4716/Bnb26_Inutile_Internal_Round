import pytest
from pydantic import ValidationError

from app.trendshort.agents.edl import build_ass, build_edl, build_srt, caption_lines
from app.trendshort.schemas import (EDL, Attribution, AudioOutput, ClipCandidate, SceneAudio, SceneVisual, ScriptOutput,
                         VisualOutput, WordStamp)

SCRIPT = ScriptOutput.model_validate({
    "title": "Fixed", "hook": "Look at this.",
    "scenes": [{"id": "s1", "narration": "Look at this.", "visual_query": "sky", "on_screen_text": "Look", "duration_sec": 3},
               {"id": "s2", "narration": "Second line here.", "visual_query": "sea", "on_screen_text": "Two", "duration_sec": 9},
               {"id": "s3", "narration": "Third and final.", "visual_query": "road", "on_screen_text": "", "duration_sec": 10}],
    "cta": "Follow.", "hashtags": ["#a"], "description": "Fixed description."})

AUDIO = AudioOutput(total_duration=6.5, scenes=[
    SceneAudio(scene_id="s1", path="/a/s1.mp3", duration_sec=1.5, tts_provider="mock", caption_provider="estimate",
               words=[WordStamp(word="Look", start=0.0, end=0.4), WordStamp(word="at", start=0.5, end=0.7),
                      WordStamp(word="this.", start=0.8, end=1.6)]),
    SceneAudio(scene_id="s2", path="/a/s2.mp3", duration_sec=2.0, tts_provider="mock", caption_provider="estimate",
               words=[WordStamp(word="Second", start=0.1, end=0.6)]),
    SceneAudio(scene_id="s3", path="/a/s3.mp3", duration_sec=3.0, tts_provider="mock", caption_provider="estimate",
               words=[WordStamp(word="Third", start=0.2, end=0.7)]),
])


def _cand(kind, path):
    return ClipCandidate(kind=kind, provider="demo", url=path, local_path=path,
                         attribution=Attribution(provider="Pexels", author="A", source_url="https://x"))


VISUALS = VisualOutput(ranking_provider="mock", scenes=[
    SceneVisual(scene_id="s1", candidates=[_cand("video", "/v/1.mp4")]),
    SceneVisual(scene_id="s2", chosen_index=1, candidates=[_cand("video", "/v/2a.mp4"), _cand("image", "/i/2b.jpg")]),
    SceneVisual(scene_id="s3", candidates=[_cand("video", "/v/3.mp4")]),
])


def test_edl_timing_driven_by_audio():
    edl = build_edl("run1", SCRIPT, AUDIO, VISUALS)
    assert [(v.start, v.duration) for v in edl.video] == [(0.0, 1.5), (1.5, 2.0), (3.5, 3.0)]
    assert [a.start for a in edl.voice] == [0.0, 1.5, 3.5]
    assert edl.total_duration == 6.5


def test_edl_uses_chosen_candidate_and_ken_burns_for_images():
    edl = build_edl("run1", SCRIPT, AUDIO, VISUALS)
    assert edl.video[1].source.path == "/i/2b.jpg" and edl.video[1].source.ken_burns
    assert not edl.video[0].source.ken_burns


def test_edl_words_absolute_and_clamped_to_scene():
    edl = build_edl("run1", SCRIPT, AUDIO, VISUALS)
    assert edl.words[2].end == 1.5                     # 1.6 clamped to the scene length
    assert edl.words[3].start == pytest.approx(1.6)    # 1.5 offset + 0.1
    assert edl.words[4].start == pytest.approx(3.7)


def test_edl_overlays_hook_first_and_skip_empty_text():
    edl = build_edl("run1", SCRIPT, AUDIO, VISUALS)
    assert edl.overlays[0].kind == "hook" and edl.overlays[0].end == 1.5
    assert len(edl.overlays) == 2


def test_edl_is_deterministic():
    a = build_edl("run1", SCRIPT, AUDIO, VISUALS).model_dump_json()
    b = build_edl("run1", SCRIPT, AUDIO, VISUALS).model_dump_json()
    assert a == b


def test_edl_rejects_gaps():
    d = build_edl("run1", SCRIPT, AUDIO, VISUALS).model_dump()
    d["video"][1]["start"] = 2.0
    with pytest.raises(ValidationError, match="expected"):
        EDL.model_validate(d)


def test_ass_and_srt_generation():
    edl = build_edl("run1", SCRIPT, AUDIO, VISUALS)
    ass = build_ass(edl)
    assert "PlayResX: 1080" in ass and "PlayResY: 1920" in ass
    assert r"{\k" in ass and "LOOK" in ass
    assert ass.count("Dialogue:") == len(edl.overlays) + len(caption_lines(edl.words, 3))
    srt = build_srt(edl)
    assert srt.startswith("1\n00:00:00,000 --> ")


def test_caption_lines_break_on_punctuation():
    ws = [WordStamp(word=w, start=i, end=i + 0.5) for i, w in enumerate("a b. c d e f".split())]
    assert [[w.word for w in l] for l in caption_lines(ws, 3)] == [["a", "b."], ["c", "d", "e"], ["f"]]
