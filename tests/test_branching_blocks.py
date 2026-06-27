"""Branching/gating activation — the `continue` (gated reveal) and `scenario`
(decision walk-through) blocks graduated from coming-soon stubs to authorable §8
grammar.

Covers: the parser produces the right IR, the `*Continue:*` gate propagates the
`gated` flag across the unit (importer parity with docx_import), the lint accepts
valid blocks and flags a scenario with no model answer, and the registry now
treats both as authorable (no longer coming-soon).
"""
import os
import tempfile

import authoring
import blocks
import md_import


def _import(md):
    f = tempfile.NamedTemporaryFile("w", suffix=".md", delete=False, encoding="utf-8")
    f.write(md)
    f.close()
    try:
        ir, _ = md_import.import_md(f.name, which=1)
    finally:
        os.unlink(f.name)
    return ir


_OBJ = ("## Microlearning 1: Branching Test\n\n"
        "**Slide 1 — Learning Objectives**\n"
        "*Visual:* graphic · obj · slot: `obj`\n"
        "- Practice a decision\n\n")


# --------------------------------------------------------------- registry flip

def test_branching_blocks_are_authorable():
    auth = blocks.authorable_types()
    assert "continue" in auth and "scenario" in auth
    cs = blocks.coming_soon_types()
    assert "continue" not in cs and "scenario" not in cs
    # headingParagraph stays the lone import-only stub
    assert "headingParagraph" in cs


# --------------------------------------------------------------- *Continue:*

def test_continue_parses_with_label_and_gates_what_follows():
    md = (_OBJ +
          "**Slide 2 — Predict**\n"
          "Make your prediction.\n"
          "*Continue:* Reveal the answer\n"
          "Here is what actually happens.\n\n"
          "**Slide 3 — After**\n"
          "More detail follows.\n")
    ir = _import(md)
    types = [b["type"] for b in ir["blocks"]]
    assert "continue" in types
    cont = next(b for b in ir["blocks"] if b["type"] == "continue")
    assert cont["text"] == "Reveal the answer"
    # the gate itself is ungated (it IS the reveal trigger)
    assert cont["gated"] is False
    # everything BEFORE the gate is ungated; everything AFTER is gated
    idx = ir["blocks"].index(cont)
    assert all(b["gated"] is False for b in ir["blocks"][:idx])
    assert all(b["gated"] is True for b in ir["blocks"][idx + 1:])


def test_continue_default_label():
    md = _OBJ + "**Slide 2 — Gate**\nBefore.\n*Continue:*\nAfter.\n"
    ir = _import(md)
    cont = next(b for b in ir["blocks"] if b["type"] == "continue")
    assert cont["text"] == "CONTINUE"


def test_no_continue_leaves_everything_ungated():
    md = _OBJ + "**Slide 2 — Plain**\nJust prose, no gate.\n"
    ir = _import(md)
    assert all(b["gated"] is False for b in ir["blocks"])


# --------------------------------------------------------------- *Scenario:*

_SCENARIO = (
    "**Slide 2 — What would you do?**\n"
    "*Scenario:*\n"
    "::: scene\n"
    "title: Urgent ICU transfer\n"
    "A nurse calls about an urgent ICU transfer with no bed assigned. What first?\n"
    "- Accept and start the bed assignment · preferred · feedback: Right — secure the bed first.\n"
    "- Ask them to submit a written request · feedback: Too slow for an urgent case.\n"
    ":::\n"
)


def test_scenario_parses_scene_narrative_and_responses():
    ir = _import(_OBJ + _SCENARIO)
    scn = next(b for b in ir["blocks"] if b["type"] == "scenario")
    assert len(scn["scenes"]) == 1
    sc = scn["scenes"][0]
    assert sc["title"] == "Urgent ICU transfer"
    assert "urgent ICU transfer" in sc["html"]
    assert len(sc["responses"]) == 2
    pref = [r for r in sc["responses"] if r.get("preferred")]
    assert len(pref) == 1
    assert "secure the bed" in pref[0]["feedback"]
    # the non-preferred choice still carries feedback, no preferred flag
    other = [r for r in sc["responses"] if not r.get("preferred")][0]
    assert "Too slow" in other["feedback"]


def test_scenario_multi_scene():
    md = (_OBJ + "**Slide 2 — Case**\n*Scenario:*\n"
          "::: scene\ntitle: One\nFirst situation.\n- Do A · preferred\n- Do B\n"
          "::: scene\ntitle: Two\nSecond situation.\n- Do C\n- Do D · preferred\n:::\n")
    ir = _import(md)
    scn = next(b for b in ir["blocks"] if b["type"] == "scenario")
    assert [s["title"] for s in scn["scenes"]] == ["One", "Two"]


def test_scenario_feedback_with_separators_survives():
    # A3: feedback prose containing the `·`/`|` chars the grammar uses elsewhere must
    # NOT be truncated — feedback: is terminal, everything after it is captured verbatim.
    md = (_OBJ + "**Slide 2 — Case**\n*Scenario:*\n::: scene\n"
          "A situation.\n"
          "- Page the attending · preferred · feedback: Correct · this escalates "
          "per policy | document the call.\n"
          "- Wait and see · feedback: Too slow — minutes matter | act now.\n"
          ":::\n")
    ir = _import(md)
    scn = next(b for b in ir["blocks"] if b["type"] == "scenario")
    resps = scn["scenes"][0]["responses"]
    pref = [r for r in resps if r.get("preferred")][0]
    # the whole remediation payload survives, including the · and | characters
    assert "this escalates per policy" in pref["feedback"]
    assert "document the call" in pref["feedback"]
    # the response text itself is unaffected (split off cleanly before feedback:)
    assert "Page the attending" in pref["html"]
    assert "feedback" not in pref["html"].lower()
    other = [r for r in resps if not r.get("preferred")][0]
    assert "minutes matter" in other["feedback"] and "act now" in other["feedback"]


# --------------------------------------------------------------- lint guardrails

def test_scenario_good_passes_lint():
    ok, _, errs = authoring.lint(_OBJ + _SCENARIO)
    assert ok, errs


def test_scenario_no_preferred_flagged():
    md = (_OBJ + "**Slide 2 — Case**\n*Scenario:*\n::: scene\n"
          "A situation.\n- Choice one · feedback: nope\n- Choice two · feedback: nope\n:::\n")
    ok, _, errs = authoring.lint(md)
    assert not ok and any("preferred" in e for e in errs), errs


def test_scenario_no_responses_flagged():
    md = (_OBJ + "**Slide 2 — Case**\n*Scenario:*\n::: scene\n"
          "title: Empty\nJust narrative, no choices.\n:::\n")
    ok, _, errs = authoring.lint(md)
    assert not ok and any("no response choices" in e for e in errs), errs


def test_continue_and_scenario_not_rejected_as_coming_soon():
    # the coming-soon lint guard must no longer fire for these two
    ok, _, errs = authoring.lint(_OBJ + _SCENARIO +
                                 "**Slide 3 — Gate**\nBefore.\n*Continue:* Next\nAfter.\n")
    assert ok, errs
    assert not any("COMING-SOON" in e for e in errs), errs
