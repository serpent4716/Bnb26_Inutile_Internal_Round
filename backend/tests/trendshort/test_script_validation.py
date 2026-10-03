import json

import pytest
from pydantic import ValidationError

from app.trendshort.agents.script_agent import assemble, estimate_seconds, fit_durations
from app.trendshort.providers.llm import extract_json
from app.trendshort.schemas import HookPart, PackagingPart, Scene, ScenesPart, ScriptOutput


def _scene(i, text="word " * 10, dur=5.0):
    return {"id": f"s{i}", "narration": text.strip(), "visual_query": "city night", "on_screen_text": "", "duration_sec": dur}


def _valid():
    return {"title": "A title", "hook": "This changes everything.",
            "scenes": [_scene(1, "This changes everything.", 3)] + [_scene(i) for i in range(2, 6)],
            "cta": "Follow for more.", "hashtags": ["science", "#facts"], "description": "A description here."}


def test_valid_script_passes_and_normalizes_hashtags():
    s = ScriptOutput.model_validate(_valid())
    assert s.hashtags == ["#science", "#facts"]
    assert 20 <= s.total_duration <= 45


def test_hook_too_long_rejected():
    d = _valid()
    d["hook"] = d["scenes"][0]["narration"] = "one two three four five six seven eight nine ten eleven"
    with pytest.raises(ValidationError, match="hook"):
        ScriptOutput.model_validate(d)


def test_first_scene_must_be_hook():
    d = _valid()
    d["scenes"][0]["narration"] = "Something else"
    with pytest.raises(ValidationError, match="hook"):
        ScriptOutput.model_validate(d)


@pytest.mark.parametrize("dur,ok", [(1.0, False), (5.0, True), (12.0, False)])
def test_total_duration_window(dur, ok):
    d = _valid()
    for s in d["scenes"][1:]:
        s["duration_sec"] = dur
    if ok:
        ScriptOutput.model_validate(d)
    else:
        with pytest.raises(ValidationError, match="total duration"):
            ScriptOutput.model_validate(d)


def test_duplicate_scene_ids_rejected():
    d = _valid()
    d["scenes"][2]["id"] = "s2"
    d["scenes"][1]["id"] = "s2"
    with pytest.raises(ValidationError, match="unique"):
        ScriptOutput.model_validate(d)


def test_extract_json_tolerates_fences_and_chatter():
    assert extract_json('```json\n{"a": 1}\n```') == {"a": 1}
    assert extract_json('Sure! Here you go: {"a": {"b": 2}} hope it helps') == {"a": {"b": 2}}
    with pytest.raises(json.JSONDecodeError):
        extract_json("no json here")


def test_assemble_builds_hook_body_cta_and_fits_window():
    hook = HookPart(title="Title", hook="Short hook here.")
    body = ScenesPart(scenes=[{"narration": "Tiny line.", "visual_query": "sky"}] * 3)
    pack = PackagingPart(on_screen_text=["a", "b"], cta="Follow.", hashtags=["x"], description="Desc text.")
    s = assemble(hook, body, pack)
    assert s.scenes[0].narration == "Short hook here." and s.scenes[-1].narration == "Follow."
    assert [x.id for x in s.scenes] == ["s1", "s2", "s3", "s4", "s5"]
    assert s.scenes[2].on_screen_text == ""          # padded when model returns too few
    assert 20 <= s.total_duration <= 45              # short draft scaled into the window


def test_fit_durations_scales_long_scripts_down():
    scenes = [Scene(id=f"s{i}", narration="x y", visual_query="qq", duration_sec=12) for i in range(6)]
    assert sum(s.duration_sec for s in fit_durations(scenes)) == pytest.approx(45, abs=0.1)
    assert estimate_seconds("one two three four five") == pytest.approx(2.3)
