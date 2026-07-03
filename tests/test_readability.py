"""C19 — voice / reading-level lint (deterministic, non-blocking).

The build report gains a `readability` section: a Flesch-Kincaid grade over the course
prose, flagged against the AUDIENCE band of the course PURPOSE preset (declared via
`*Preset:*` → ir['preset']), plus an over-long-sentence signal. Every finding is
advisory (info/warn) and NEVER flips the build `ok` — same non-blocking model as M2's
a11y findings. All deterministic: no metered API.
"""
import os
import tempfile

import build_report as br
import md_import


def _ir(blocks, **kw):
    ir = {"title": "T", "blocks": blocks, "_stats": {"blocks": len(blocks)}}
    ir.update(kw)
    return ir


_SIMPLE = ("The cat sat on the mat. The dog ran fast. We go home now. "
           "It is a nice day. Birds sing in the tree. She likes to read. " * 3)
_DENSE = ("The utilization of multifaceted interdisciplinary methodologies necessitates "
          "comprehensive organizational recalibration, consequently engendering substantial "
          "operational transformations throughout the institutional infrastructure "
          "notwithstanding considerable stakeholder resistance and entrenched bureaucratic "
          "inertia. " * 3)


def _grade(findings):
    return next(f for f in findings if f["check"] == "reading-level" and f["severity"] == "info")


# --- the Flesch-Kincaid engine ------------------------------------------------

def test_simple_prose_reads_lower_than_dense_prose():
    g_simple = _fk(_SIMPLE)
    g_dense = _fk(_DENSE)
    assert g_simple < g_dense
    assert g_dense > 12          # the dense paragraph is genuinely college+ level


def _fk(text):
    grade, _ease, _w, _s = br._fk_stats(text)
    return grade


def test_too_little_prose_is_not_assessed():
    assert br.readability_findings(_ir([{"type": "paragraph", "html": "Hi there."}])) == []


def test_syllable_counter_is_sane():
    assert br._syllables("cat") == 1
    assert br._syllables("running") == 2
    assert br._syllables("organization") >= 4


# --- audience-band flagging ---------------------------------------------------

def test_dense_prose_flagged_under_onboarding_band():
    f = br.readability_findings(_ir([{"type": "paragraph", "html": _DENSE}]), preset="onboarding")
    assert any(x["severity"] == "warn" and x["check"] == "reading-level" for x in f)
    assert "grade 9" in _grade(f)["message"]        # onboarding band surfaced


def test_same_prose_not_flagged_under_lenient_standard_band():
    # grade ~12.2 sits between the onboarding (9) and standard (14) bands → warn only for onboarding.
    mid = _ir([{"type": "paragraph", "html":
                ("The transfer coordinator reviews each incoming request and confirms the receiving "
                 "unit has adequate capacity before assigning a bed to the patient. This process "
                 "maintains steady patient flow. " * 4)}])
    onb = br.readability_findings(mid, preset="onboarding")
    std = br.readability_findings(mid, preset="standard")
    assert any(x["severity"] == "warn" for x in onb)
    assert not any(x["severity"] == "warn" and x["check"] == "reading-level" for x in std)


def test_band_comes_from_ir_preset_when_no_kwarg():
    ir = _ir([{"type": "paragraph", "html": _DENSE}], preset="onboarding")
    f = br.readability_findings(ir)          # no preset kwarg → uses ir['preset']
    assert any(x["severity"] == "warn" for x in f)


def test_unknown_preset_falls_back_to_standard_band():
    f = br.readability_findings(_ir([{"type": "paragraph", "html": _DENSE}]), preset="bogus")
    assert "grade 14" in _grade(f)["message"]


# --- voice / sentence-length signal -------------------------------------------

def test_over_long_sentence_is_flagged():
    run_on = "This " + "and that ".join(["clause"] * 25) + " finally ends here."
    f = br.readability_findings(_ir([{"type": "paragraph", "html": run_on + " " + _SIMPLE}]))
    assert any(x["check"] == "sentence-length" and x["severity"] == "warn" for x in f)


# --- non-blocking integration + wiring ----------------------------------------

def test_readability_rides_in_report_but_never_flips_ok():
    report = br.assemble(_ir([{"type": "paragraph", "html": _DENSE}]), preset="onboarding")
    assert report["ok"] is True                       # advisory only
    assert any(x["severity"] == "warn" for x in report["readability"])


def test_bank_children_prose_is_counted():
    # questionBank pools are walked so a dense pooled question still reads on the report.
    ir = _ir([{"type": "questionBank", "draw": 1,
               "questions": [{"type": "knowledgeCheck", "prompt": _DENSE, "options": []}]}])
    f = br.readability_findings(ir, preset="onboarding")
    assert any(x["severity"] == "warn" for x in f)


def test_preset_marker_parsed_into_ir():
    md = """# Course

*Preset:* onboarding

## Microlearning 1: Unit

**Slide 1 — Intro**
Welcome aboard.
"""
    fp = tempfile.NamedTemporaryFile("w", suffix=".md", delete=False, encoding="utf-8")
    fp.write(md); fp.close()
    try:
        ir, _ = md_import.import_md(fp.name)
    finally:
        os.unlink(fp.name)
    assert ir.get("preset") == "onboarding"


def test_no_preset_marker_leaves_ir_byte_identical():
    md = """# Course

## Microlearning 1: Unit

**Slide 1 — Intro**
Hello there.
"""
    fp = tempfile.NamedTemporaryFile("w", suffix=".md", delete=False, encoding="utf-8")
    fp.write(md); fp.close()
    try:
        ir, _ = md_import.import_md(fp.name)
    finally:
        os.unlink(fp.name)
    assert "preset" not in ir           # absent marker → no key (byte-identical)
