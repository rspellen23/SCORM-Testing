"""C20 — consistency check on appended content (term / voice drift).

When a unit is added to an existing multi-unit course it can DRIFT from the rest:
its reading level lands far from its siblings (voice), or it writes a product name
with different casing / introduces a non-approved term the other units avoid (terms).
`build_report.consistency_findings` flags that drift; every finding is a warning and
NEVER flips the build `ok` (same non-blocking model as C19/M2). All deterministic —
no metered API. `consistency_findings_course` runs it for every unit of a build, and
the CLI `consistency` subcommand checks one appended unit against the rest.
"""
import os

import build_report as br


def _ir(text):
    """A minimal Course IR carrying `text` as one paragraph of learner-facing prose."""
    return {"title": "T", "blocks": [{"type": "paragraph", "html": text}]}


# Enough plain, low-grade prose to clear the _fk_stats 20-word floor.
_SIMPLE = ("The team logs in each day. They pick a task and go. "
           "We track each bed and each move. It is fast and clear. "
           "A nurse asks for a bed. The tool finds one that fits. " * 2)
# Dense, high-grade prose on the SAME topic — the voice-drift target.
_DENSE = ("The orchestration of interdepartmental patient-throughput optimization "
          "necessitates comprehensive recalibration of the institutional bed-management "
          "infrastructure, consequently engendering substantial operational transformation "
          "notwithstanding entrenched procedural inertia and considerable stakeholder "
          "resistance across the enterprise. " * 2)


def _checks(findings, check):
    return [f for f in findings if f["check"] == check]


# --- nothing to compare against ----------------------------------------------

def test_no_prior_units_is_empty():
    assert br.consistency_findings(_ir(_SIMPLE), []) == []


def test_single_unit_course_sweep_is_empty():
    assert br.consistency_findings_course([_ir(_SIMPLE)]) == []


def test_non_dict_new_ir_is_empty():
    assert br.consistency_findings("nope", [_ir(_SIMPLE)]) == []


# --- voice drift --------------------------------------------------------------

def test_voice_drift_flagged_when_reading_level_diverges():
    prior = [_ir(_SIMPLE), _ir(_SIMPLE)]
    f = br.consistency_findings(_ir(_DENSE), prior)
    vd = _checks(f, "voice-drift")
    assert vd, "a much denser appended unit should flag voice drift"
    assert "harder" in vd[0]["message"]
    assert vd[0]["severity"] == "warn"


def test_no_voice_drift_when_reading_levels_match():
    prior = [_ir(_SIMPLE), _ir(_SIMPLE)]
    assert _checks(br.consistency_findings(_ir(_SIMPLE), prior), "voice-drift") == []


def test_voice_drift_reports_simpler_direction():
    prior = [_ir(_DENSE), _ir(_DENSE)]
    f = _checks(br.consistency_findings(_ir(_SIMPLE), prior), "voice-drift")
    assert f and "simpler" in f[0]["message"]


# --- term casing / spelling drift --------------------------------------------

def test_term_casing_drift_flagged():
    prior = [_ir("The team uses Transfer IQ Pro every shift. "
                 "Transfer IQ Pro shows every bed. " + _SIMPLE)]
    # appended unit lowercases the established product name
    new = _ir("Our staff open transfer iq pro at the start. " + _SIMPLE)
    f = _checks(br.consistency_findings(new, prior), "term-drift")
    assert f, "a lowercased variant of an established proper term should flag"
    assert "Transfer IQ Pro" in f[0]["message"]
    assert "transfer iq pro" in f[0]["message"]


def test_consistent_term_casing_is_not_flagged():
    prior = [_ir("The team uses Transfer IQ Pro every shift. " + _SIMPLE)]
    new = _ir("The new hire also uses Transfer IQ Pro daily. " + _SIMPLE)
    assert _checks(br.consistency_findings(new, prior), "term-drift") == []


def test_sentence_initial_capital_is_not_a_term():
    # "Birds" / "She" open sentences but aren't a multi-word proper phrase → no drift
    prior = [_ir(_SIMPLE)]
    new = _ir("Nurses log in. Birds sing. She reads. " + _SIMPLE)
    assert _checks(br.consistency_findings(new, prior), "term-drift") == []


# --- glossary drift (only when the rest avoids it) ---------------------------

_GLOSS = {"preferred": [{"term": "Transfer IQ Pro", "instead_of": ["the transfer tool"]}],
          "banned": ["utilize"]}


def test_glossary_wrong_term_in_appended_unit_only_is_drift():
    prior = [_ir("The team uses Transfer IQ Pro every shift. " + _SIMPLE)]
    new = _ir("New hires open the transfer tool to start. " + _SIMPLE)
    f = _checks(br.consistency_findings(new, prior, glossary=_GLOSS), "term-drift")
    assert any("transfer tool" in x["message"] for x in f)


def test_glossary_issue_present_in_all_units_is_not_drift():
    # if the whole course already says "the transfer tool", it's a course-wide
    # glossary miss (lint/C16), NOT a DRIFT of the appended unit
    prior = [_ir("The team opens the transfer tool. " + _SIMPLE)]
    new = _ir("New hires open the transfer tool too. " + _SIMPLE)
    f = _checks(br.consistency_findings(new, prior, glossary=_GLOSS), "term-drift")
    assert not any("transfer tool" in x["message"] for x in f)


def test_banned_word_introduced_by_appended_unit_is_drift():
    prior = [_ir("The team opens the app each day. " + _SIMPLE)]
    new = _ir("New hires utilize the app to begin. " + _SIMPLE)
    f = _checks(br.consistency_findings(new, prior, glossary=_GLOSS), "term-drift")
    assert any("utilize" in x["message"] for x in f)


# --- the whole-course sweep + report wiring ----------------------------------

def test_course_sweep_tags_findings_by_unit():
    units = [_ir(_SIMPLE), _ir(_SIMPLE), _ir(_DENSE)]
    f = br.consistency_findings_course(units)
    assert f, "the dense third unit should surface in the sweep"
    assert any(x["where"] == "unit 3" for x in f)
    assert all(x["severity"] == "warn" for x in f)


def test_consistency_rides_in_report_but_never_flips_ok():
    cons = [{"check": "voice-drift", "severity": "warn", "where": "unit 3", "message": "x"}]
    report = br.assemble({"title": "T", "_stats": {}}, consistency=cons)
    assert report["consistency"] == cons
    assert report["ok"] is True                     # non-blocking


def test_report_consistency_defaults_empty():
    report = br.assemble({"title": "T", "_stats": {}})
    assert report["consistency"] == []


# --- CLI end-to-end -----------------------------------------------------------

_COURSE_MD = """**Subject:** Bed Management
**Learning Objectives:** Learn the tool.

## Microlearning 1: Getting started

**Slide 1 — The basics**
The team uses Transfer IQ Pro every shift. Transfer IQ Pro shows every open bed. A nurse asks for a bed and the tool finds one that fits. We track each move. It is fast and clear for a new hire on the very first day of work here.

## Microlearning 2: Advanced flow

**Slide 1 — Going deeper**
The orchestration of interdepartmental patient-throughput optimization within transfer iq pro necessitates comprehensive recalibration of the institutional bed-management infrastructure, consequently engendering substantial operational transformation notwithstanding entrenched procedural inertia and considerable stakeholder resistance across every enterprise.
"""


def test_cli_consistency_flags_the_appended_unit(tmp_path, capsys):
    import cli
    md = tmp_path / "course.md"
    md.write_text(_COURSE_MD, encoding="utf-8")
    ns = type("A", (), {"md": str(md), "which": 2, "brand": "_default"})()
    cli.cmd_consistency(ns)
    out = capsys.readouterr().out
    assert "unit 2 of 2" in out
    # unit 2 both lowercases the product name AND reads much denser than unit 1
    assert "term-drift" in out or "Transfer IQ Pro" in out


def test_cli_consistency_needs_two_units(tmp_path, capsys):
    import cli
    one = "# Solo\n\n## Microlearning 1: Only\n\n*Objective:* x\n\n" + _SIMPLE + "\n"
    md = tmp_path / "solo.md"
    md.write_text(one, encoding="utf-8")
    ns = type("A", (), {"md": str(md), "which": None, "brand": "_default"})()
    cli.cmd_consistency(ns)
    assert "two or more" in capsys.readouterr().out
