"""M13 — aggregate / final quiz + section pass thresholds + subscore reporting.

A graded course can now roll its knowledge checks up into per-section OBJECTIVES:
`*Section:* blue · <Name> · pass <N>` around a KC names a scored objective (KCs that
share a name merge into one subscore). Only KCs inside a graded section are summative
(inline KCs stay formative). `*Gate:* on|off` (default on for graded courses) and the
build-time `--no-gate` control whether a failing score blocks completion. The render
emits `data-obj` per KC and `data-gate`/`data-objectives` on <body>; the player-side
aggregate/gating math is pinned in tests/test_player.js (node --test).

Byte-identical discipline: a plain `*Section:* <color>` (no name/pass) and a graded
course with no named sections and gate on produce the SAME IR/HTML as before M13.
"""
import json
import os
import tempfile

import authoring
import md_import
import render
import brand as brandlib
from ir_validate import validate_ir


def _import(md, which=1):
    f = tempfile.NamedTemporaryFile("w", suffix=".md", delete=False, encoding="utf-8")
    f.write(md)
    f.close()
    try:
        return md_import.import_md(f.name, which=which)
    finally:
        os.unlink(f.name)


def _render_body(ir, gate=None):
    d = tempfile.mkdtemp()
    render.render_course(ir, os.path.join(d, "c"), brand=brandlib.load_brand("_default"), gate=gate)
    return open(os.path.join(d, "c", "index.html"), encoding="utf-8").read()


_GRADED = """# Course

*Graded:* pass 80

## Microlearning 1: Unit

**Slide 1 — Knowledge Check**
*Section:* blue · Medication Safety · pass 70
*Question:* First safety question?
- A) Right
- B) Wrong
*Correct Answer:* A

**Slide 2 — Knowledge Check**
*Section:* blue · Medication Safety · pass 70
*Question:* Second safety question?
- A) Right
- B) Wrong
*Correct Answer:* A

**Slide 3 — Knowledge Check**
*Question:* An inline, formative check?
- A) Right
- B) Wrong
*Correct Answer:* A
"""


# --- grammar: _section_block --------------------------------------------------

def test_section_block_plain_color_is_byte_identical():
    # A bare color section gains NO M13 keys — unchanged visual band.
    assert md_import._section_block("blue") == {"type": "sectionStart", "color": "blue"}
    assert md_import._section_block("end") == {"type": "sectionEnd"}


def test_section_block_parses_name_and_pass():
    b = md_import._section_block("blue · Medication Safety · pass 70")
    assert b == {"type": "sectionStart", "color": "blue", "name": "Medication Safety",
                 "graded": True, "pass": 70}


def test_section_block_name_without_pass_is_graded_no_threshold():
    b = md_import._section_block("gold · Billing")
    assert b["graded"] is True and b["name"] == "Billing" and "pass" not in b


def test_section_block_quiz_marker_grades_without_name():
    b = md_import._section_block("teal · quiz")
    assert b["graded"] is True and "name" not in b


def test_section_block_defaults_color_green_when_first_seg_is_name():
    b = md_import._section_block("Safety · pass 60")
    assert b["color"] == "green" and b["name"] == "Safety" and b["pass"] == 60


def test_section_block_clamps_pass():
    assert md_import._section_block("blue · X · pass 250")["pass"] == 100


# --- IR: objectives + gate ----------------------------------------------------

def test_graded_sections_become_objectives():
    ir, _ = _import(_GRADED)
    assert ir["graded"] is True
    assert ir["objectives"] == [{"id": "medication-safety", "name": "Medication Safety", "pass": 70}]


def test_kcs_tagged_with_objective_inline_kc_is_formative():
    ir, _ = _import(_GRADED)
    kcs = [b for b in ir["blocks"] if b["type"] == "knowledgeCheck"]
    assert [k.get("objective") for k in kcs] == ["medication-safety", "medication-safety", None]


def test_gate_defaults_on_for_graded_course():
    ir, _ = _import(_GRADED)
    assert ir["gateCompletion"] is True


def test_gate_off_directive():
    ir, _ = _import(_GRADED.replace("*Graded:* pass 80", "*Graded:* pass 80\n*Gate:* off"))
    assert ir["gateCompletion"] is False


def test_gate_on_directive_explicit():
    ir, _ = _import(_GRADED.replace("*Graded:* pass 80", "*Graded:* pass 80\n*Gate:* on"))
    assert ir["gateCompletion"] is True


def test_same_section_name_merges_into_one_objective():
    # two KCs, same section name → one objective, both tagged
    ir, _ = _import(_GRADED)
    assert len(ir["objectives"]) == 1


def test_later_section_supplies_missing_threshold():
    md = _GRADED.replace("*Section:* blue · Medication Safety · pass 70\n*Question:* First",
                         "*Section:* blue · Medication Safety\n*Question:* First", 1)
    # first occurrence has no pass, second still declares pass 70 → merged objective gets 70
    ir, _ = _import(md)
    assert ir["objectives"][0]["pass"] == 70


def test_objective_without_threshold_has_null_pass():
    md = _GRADED.replace(" · pass 70", "")
    ir, _ = _import(md)
    assert ir["objectives"] == [{"id": "medication-safety", "name": "Medication Safety", "pass": None}]


# --- IR schema ----------------------------------------------------------------

def test_ir_validates_against_schema():
    ir, _ = _import(_GRADED)
    validate_ir(ir, label="m13")  # raises on schema violation


# --- byte-identical when the feature is off -----------------------------------

def test_ungraded_course_has_no_gate_or_objectives_keys_effect():
    md = _GRADED.replace("*Graded:* pass 80\n\n", "")
    ir, _ = _import(md)
    assert ir["graded"] is False
    # objectives only populate from graded sections; without *Graded* the sections
    # still parse but they're just visual — no KC is tagged.
    assert ir["objectives"] == [] or all(k.get("objective") is None
                                         for k in ir["blocks"] if k["type"] == "knowledgeCheck")


def test_plain_graded_course_render_has_no_m13_attrs():
    md = """# C

*Graded:* pass 80

## Microlearning 1: U

**Slide 1 — Knowledge Check**
*Question:* Q?
- A) a
- B) b
*Correct Answer:* A
"""
    ir, _ = _import(md)
    html = _render_body(ir)
    assert 'data-graded="1"' in html and 'data-pass="80"' in html
    assert "data-gate" not in html and "data-objectives" not in html and "data-obj=" not in html


# --- render: data attributes --------------------------------------------------

def test_render_emits_data_obj_and_objectives():
    ir, _ = _import(_GRADED)
    html = _render_body(ir)
    assert html.count("data-obj=") == 2                     # two tagged KCs
    assert "data-objectives=" in html
    # the objectives JSON round-trips out of the attribute (HTML-unescaped)
    import re
    m = re.search(r'data-objectives="([^"]*)"', html)
    payload = json.loads(m.group(1).replace("&quot;", '"'))
    assert payload == [{"id": "medication-safety", "name": "Medication Safety", "pass": 70}]


def test_render_gate_off_directive_emits_data_gate_zero():
    ir, _ = _import(_GRADED.replace("*Graded:* pass 80", "*Graded:* pass 80\n*Gate:* off"))
    assert 'data-gate="0"' in _render_body(ir)


def test_render_gate_override_forces_off():
    ir, _ = _import(_GRADED)                                 # gateCompletion True
    assert 'data-gate="0"' not in _render_body(ir, gate=None)
    assert 'data-gate="0"' in _render_body(ir, gate=False)   # build override


def test_render_gate_override_none_respects_ir():
    ir, _ = _import(_GRADED.replace("*Graded:* pass 80", "*Graded:* pass 80\n*Gate:* off"))
    assert 'data-gate="0"' in _render_body(ir, gate=None)    # None = honor the directive


# --- lint ---------------------------------------------------------------------

def test_lint_flags_section_threshold_on_ungraded_course():
    md = """# C

## Microlearning 1: U

**Slide 1 — Knowledge Check**
*Section:* blue · Safety · pass 70
*Question:* Q?
- A) a
- B) b
*Correct Answer:* A
"""
    ok, n, errors = authoring.lint(md)
    assert not ok
    assert any("isn't graded" in e for e in errors)


def test_lint_accepts_section_threshold_on_graded_course():
    ok, n, errors = authoring.lint(_GRADED)
    assert ok, errors
