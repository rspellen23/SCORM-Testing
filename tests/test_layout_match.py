"""Tests for the deterministic intent → layout matcher (capability P4).

`match_layout_from_intent` formalizes the LAYOUT_MATCH / LAYOUT_PURPOSE prose into a
real scoring function so an operator can describe a slide in a sentence and get a
real layout instead of a generic bullet list. It is pure and deterministic — no LLM
call — which is exactly why it is unit-testable here.
"""
import authoring
from authoring import (LAYOUT_CUES, LAYOUT_PURPOSE, _IMAGE_LAYOUTS, _LAYOUT_ORDER,
                       match_layout_from_intent)


# ── the cue table stays faithful to the real layout vocabulary ────────────────
def test_every_cue_key_is_a_real_layout():
    """Guards against drift: a cue table key that isn't a real deck layout would
    recommend a layout the generator/renderer can't emit."""
    valid = set(_LAYOUT_ORDER) | set(_IMAGE_LAYOUTS)
    for layout in LAYOUT_CUES:
        assert layout in valid, f"{layout} is not a deck layout"
        assert layout in LAYOUT_PURPOSE, f"{layout} missing a LAYOUT_PURPOSE hint"


def test_cues_are_non_empty_and_lowercase():
    for layout, cues in LAYOUT_CUES.items():
        assert cues, f"{layout} has no cues"
        for c in cues:
            assert c == c.lower(), f"cue {c!r} must be lowercase for matching"


# ── the canonical LAYOUT_MATCH five each resolve to their layout ──────────────
def test_doc_example_compare_deployment_models():
    """The capability doc's own example: 'compare the 3 deployment models'."""
    res = match_layout_from_intent("compare the 3 deployment models")
    assert res["recommended"] == "comparison"
    assert res["confident"] is True


def test_process_intent():
    res = match_layout_from_intent("walk the learner through the steps to submit a request")
    assert res["recommended"] == "process"


def test_timeline_intent():
    res = match_layout_from_intent("the product roadmap over the next three quarters")
    assert res["recommended"] == "timeline"
    assert res["confident"] is True  # roadmap + quarters both hit


def test_infographic_intent():
    res = match_layout_from_intent("frame the problem, the framework, and our goals")
    assert res["recommended"] == "infographic"


def test_divider_intent():
    res = match_layout_from_intent("a title slide for the section")
    assert res["recommended"] == "divider"


def test_cycles_intent():
    res = match_layout_from_intent("our continuous improvement loop")
    assert res["recommended"] == "cycles"
    assert res["confident"] is True  # loop + continuous


def test_comparison_beats_infographic_on_ties():
    """'compare' (comparison) should win outright here; nothing else fires."""
    res = match_layout_from_intent("compare option A and option B")
    assert res["recommended"] == "comparison"


# ── structure of the result ───────────────────────────────────────────────────
def test_result_shape_and_ranked_sorted():
    res = match_layout_from_intent("a roadmap of phases and milestones over time")
    assert set(res) == {"intent", "recommended", "confident", "ranked"}
    scores = [r["score"] for r in res["ranked"]]
    assert scores == sorted(scores, reverse=True)  # sorted by score desc
    top = res["ranked"][0]
    assert set(top) == {"layout", "score", "cues"}
    assert top["layout"] == res["recommended"]
    assert top["cues"]  # the winning layout reports which cues fired


def test_ranked_only_contains_matched_layouts():
    res = match_layout_from_intent("compare A vs B")
    for r in res["ranked"]:
        assert r["score"] >= 1


def test_tie_breaks_by_layout_order():
    """When two layouts tie on score, the one earlier in _LAYOUT_ORDER wins."""
    # craft an intent hitting exactly one cue for two layouts of equal score
    res = match_layout_from_intent("an agenda and a closing")  # agenda(1) vs closing(1)
    order = {n: i for i, n in enumerate(_LAYOUT_ORDER)}
    layouts = [r["layout"] for r in res["ranked"]]
    assert layouts == sorted(layouts, key=lambda x: order[x])
    assert res["recommended"] == "agenda"  # agenda precedes closing in _LAYOUT_ORDER
    assert res["confident"] is False       # a genuine tie is not confident


# ── vague / empty intent falls back honestly ──────────────────────────────────
def test_vague_intent_falls_back_to_bullets_not_confident():
    res = match_layout_from_intent("some general information about the product")
    assert res["recommended"] == "bullets"
    assert res["confident"] is False
    assert res["ranked"] == []


def test_empty_intent():
    for bad in ["", "   ", None]:
        res = match_layout_from_intent(bad)
        assert res["recommended"] == "bullets"
        assert res["confident"] is False


# ── whole-word matching avoids substring false positives ──────────────────────
def test_whole_word_token_does_not_match_inside_another_word():
    # "misstep" contains "step" but must NOT trigger the process layout on its own
    res = match_layout_from_intent("a misstep in judgment")
    assert res["ranked"] == []
    assert res["recommended"] == "bullets"


def test_phrase_cue_matches_as_substring():
    res = match_layout_from_intent("show these side-by-side")
    assert res["recommended"] == "comparison"


# ── image layouts are gated behind allow_image_layouts ────────────────────────
def test_image_layouts_excluded_by_default():
    res = match_layout_from_intent("a hero image of the dashboard")
    assert all(r["layout"] not in _IMAGE_LAYOUTS for r in res["ranked"])


def test_image_layouts_included_when_allowed():
    res = match_layout_from_intent("a hero image of the dashboard", allow_image_layouts=True)
    assert res["recommended"] == "image"


# ── determinism: same input, byte-identical output ────────────────────────────
def test_deterministic():
    a = match_layout_from_intent("compare the deployment models and the rollout timeline")
    b = match_layout_from_intent("compare the deployment models and the rollout timeline")
    assert a == b
