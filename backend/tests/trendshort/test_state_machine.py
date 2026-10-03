import pytest

from app.trendshort.state_machine import InvalidTransition, can_transition, downstream, transition


def test_happy_path():
    path = ["trend_selected", "scripting", "voicing", "sourcing_visuals", "assembling",
            "ready_for_review", "publishing", "published"]
    s = path[0]
    for nxt in path[1:]:
        s = transition(s, nxt)
    assert s == "published"


@pytest.mark.parametrize("a,b", [("trend_selected", "voicing"), ("scripting", "assembling"),
                                 ("voicing", "published"), ("trend_selected", "ready_for_review")])
def test_cannot_skip_forward(a, b):
    with pytest.raises(InvalidTransition):
        transition(a, b)


def test_any_active_state_can_fail_but_published_cannot():
    for s in ["trend_selected", "scripting", "voicing", "sourcing_visuals", "assembling", "ready_for_review", "publishing"]:
        assert can_transition(s, "failed")
    assert not can_transition("published", "failed")


def test_rewind_for_rerun_and_edits():
    assert can_transition("ready_for_review", "scripting")
    assert can_transition("ready_for_review", "assembling")
    assert can_transition("assembling", "voicing")
    assert can_transition("published", "assembling")
    assert not can_transition("scripting", "assembling")      # forward jumps are not rewinds


def test_failed_can_resume_any_stage():
    for s in ["scripting", "voicing", "sourcing_visuals", "assembling"]:
        assert can_transition("failed", s)


def test_republish():
    assert can_transition("published", "publishing")


def test_unknown_states_rejected():
    assert not can_transition("scripting", "dancing")


def test_stale_propagation_graph():
    assert downstream("script") == ["audio", "visuals", "assembly"]
    assert downstream("audio") == ["visuals", "assembly"]
    assert downstream("visuals") == ["assembly"]
    assert downstream("assembly") == []
