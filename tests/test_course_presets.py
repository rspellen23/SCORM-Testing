"""Course PURPOSE presets + auto-derived objectives (generation power).

COURSE_PRESETS is the course-side analogue of DECK_PRESETS — a prompt-layer profile
that shapes VOICE/DEPTH, ASSESSMENT posture, and LENGTH, orthogonal to the archetype.
Auto-derived objectives: the plan asks for measurable outcomes per unit, and the unit
prompt requires Slide 1 to open with an *Objectives:* block seeded from that plan
objective (so plan and rendered objectives stay consistent).
"""
import os
import re

import authoring as A

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

_PLAN = lambda preset=None: A.build_plan_prompt("o", "a", "concept-explainer", None, "SRC", preset=preset)
_UNIT = lambda preset=None, obj="identify X; decide Y": A.build_unit_prompt(
    {"title": "U", "objective": obj}, [{"title": "U", "objective": obj}], 1, 1,
    "o", "a", "concept-explainer", "SRC", preset=preset)
_DRAFT = lambda preset=None: A.build_prompt("o", "a", "concept-explainer", None, "SRC", preset=preset)


# --- preset injection ------------------------------------------------------

def test_standard_and_unknown_inject_nothing():
    for preset in ("standard", None, "", "nonsense"):
        for prompt in (_PLAN(preset), _UNIT(preset), _DRAFT(preset)):
            assert "COURSE PURPOSE" not in prompt
            assert "SRC" in prompt          # the core prompt still assembles


def test_every_real_preset_injects_voice_and_assessment():
    for key, spec in A.COURSE_PRESETS.items():
        if key == "standard":
            continue
        for prompt in (_PLAN(key), _UNIT(key), _DRAFT(key)):
            assert "COURSE PURPOSE" in prompt
            assert spec["label"] in prompt
            assert "VOICE & DEPTH" in prompt and "ASSESSMENT POSTURE" in prompt


def test_presets_differ_in_voice():
    assert A.course_preset_directive("compliance") != A.course_preset_directive("onboarding")
    assert "authoritative" in _UNIT("compliance").lower()
    assert "welcoming" in _UNIT("onboarding").lower()


def test_directive_robust_to_bad_input():
    for junk in (None, "", "xyz", 123, {}, []):
        out = A.course_preset_directive(junk)
        assert out == "" or isinstance(out, str)


def test_list_course_presets_shape():
    presets = A.list_course_presets()
    assert {p["key"] for p in presets} == set(A.COURSE_PRESETS)
    assert all(p.get("label") and p.get("desc") for p in presets)


# --- auto-derived objectives ----------------------------------------------

def test_plan_asks_for_measurable_outcomes():
    assert "MEASURABLE outcomes" in _PLAN()


def test_unit_prompt_seeds_objectives_from_plan():
    up = _UNIT(obj="triage an urgent transfer; escalate correctly")
    assert "AUTO-DERIVED OBJECTIVES" in up
    assert "*Objectives:*" in up
    # the unit's plan objective is echoed into the prompt as the seed
    assert "triage an urgent transfer; escalate correctly" in up


# --- dashboard drift guard (mirrors the deck preset selector test) ---------

def test_dashboard_selector_matches_preset_table():
    """Every COURSE_PRESETS key must appear as an <option> in the course tab's
    #gen_preset selector, and vice-versa — the UI can't list a preset the backend
    doesn't honor (or omit one it does)."""
    html = open(os.path.join(REPO, "dashboard", "index.html"), encoding="utf-8").read()
    sel = html.split('id="gen_preset"', 1)[1].split("</select>", 1)[0]
    opts = set(re.findall(r'<option value="([^"]*)"', sel))
    assert opts == set(A.COURSE_PRESETS), (opts, set(A.COURSE_PRESETS))
