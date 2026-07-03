"""M5 — one-source → translated course.

`translate_course` runs one subscription-CLI pass per `## Microlearning N:` unit,
reassembles, and verifies the §8 block structure survived. `resolve_target` picks
translate vs localize; the M4 glossary feeds a KEEP-VERBATIM term list + banned
words into the prompt. No metered calls — `run_cli` is the stubbed seam.
"""
import re

import authoring as A


# A minimal but valid two-unit §8 course (Slide-1 objectives + a KC per unit).
SRC = """# Transfer Basics

**Curriculum Rationale:** Teach intake, then routing.

## Microlearning 1: Intake

**Slide 1 — Learning Objectives**
*Visual:* graphic · an overview of intake
*Objectives:* After this lesson, you will be able to:
- Identify a transfer request
- Decide the intake queue

**Slide 2 — What is intake**
Intake is the first step where a request enters the system.

**Slide 3 — Knowledge Check**
*Question:* Where does a request enter first?
- A) Intake
- B) Discharge
*Correct Answer:* A
*Feedback — Correct:* Right — intake is the front door.
*Feedback — Incorrect:* Not quite — start at intake.

## Microlearning 2: Routing

**Slide 1 — Learning Objectives**
*Visual:* graphic · how routing works
*Objectives:* After this lesson, you will be able to:
- Route a request to the right queue

**Slide 2 — Routing rules**
Route each request by urgency and unit.
"""


# ---- run_cli stubs ------------------------------------------------------------

def _chunk_of(prompt):
    """Pull the fragment the prompt asked to translate back out of the prompt."""
    m = re.search(r"MARKDOWN TO (?:TRANSLATE|LOCALIZE) =+\n(.*)\n=+ END =+", prompt, re.S)
    return m.group(1) if m else ""


def _echo_cli(prompt, record=None):
    chunk = _chunk_of(prompt)
    if record is not None:
        record.append(prompt)
    return (True, chunk, "")


# ---- resolve_target -----------------------------------------------------------

def test_resolve_target_translate_for_language():
    assert A.resolve_target("Spanish") == {"name": "Spanish", "mode": "translate"}
    assert A.resolve_target("fr")["mode"] == "translate"


def test_resolve_target_localize_for_english_dialects():
    for t in ("en-GB", "UK", "British English", "en_gb", "en-uk"):
        r = A.resolve_target(t)
        assert r["mode"] == "localize", t
    # any en-XX is a locale, not a language
    assert A.resolve_target("en-AU")["mode"] == "localize"


def test_resolve_target_empty_is_safe():
    assert A.resolve_target("")["mode"] == "translate"


# ---- glossary keep-verbatim terms --------------------------------------------

def test_glossary_keep_terms():
    g = {"preferred": [{"term": "Transfer IQ Pro"}, {"term": ""}, {"term": "Nova"}], "banned": ["synergy"]}
    assert A.glossary_keep_terms(g) == ["Transfer IQ Pro", "Nova"]
    assert A.glossary_keep_terms(None) == []


# ---- prompt content -----------------------------------------------------------

def test_prompt_preserves_structural_tokens_and_terms():
    g = {"preferred": [{"term": "Transfer IQ Pro"}], "banned": ["synergy"]}
    p = A.build_translate_prompt("## Microlearning 1: X\n", "Spanish", mode="translate",
                                 keep_terms=["Transfer IQ Pro"], glossary=g)
    assert "TRANSLATE this course markdown into Spanish" in p
    assert "`*Correct Answer:*`" in p and "`*Question:*`" in p and "`*Visual:*`" in p
    assert "option letters `- A)`" in p
    assert "NUMBERS ARE DATA" in p
    assert "KEEP THESE PRODUCT/BRAND TERMS VERBATIM" in p and "Transfer IQ Pro" in p
    assert "banned words: synergy" in p


def test_prompt_localize_mode_stays_english():
    p = A.build_translate_prompt("x", "British English (en-GB)", mode="localize")
    assert "LOCALIZE this course markdown" in p
    assert "keep it English" in p
    assert "MINIMUM changes" in p


# ---- structure fingerprint + diff --------------------------------------------

def test_course_structure_and_diff_identical():
    s = A.course_structure(SRC)
    assert len(s) == 2
    assert all(seq for seq in s)                 # both units parsed to some blocks
    assert A.structure_diff(s, s) == []          # identical to itself


def test_structure_diff_flags_unit_count_change():
    s = A.course_structure(SRC)
    issues = A.structure_diff(s, s[:1])
    assert issues and "unit count changed" in issues[0]


def test_structure_diff_flags_block_drift():
    a = [["objectives", "text", "knowledgeCheck"], ["objectives", "text"]]
    b = [["objectives", "text"], ["objectives", "text"]]           # unit 1 lost a block
    issues = A.structure_diff(a, b)
    assert len(issues) == 1 and "unit 1" in issues[0]


# ---- end-to-end orchestration (stubbed provider) ------------------------------

def test_translate_course_identity_preserves_structure(monkeypatch):
    prompts = []
    monkeypatch.setattr(A, "run_cli", lambda prov, prompt, **k: _echo_cli(prompt, prompts))
    monkeypatch.setattr(A, "load_glossary", lambda b=None: {"preferred": [], "banned": []})
    res = A.translate_course("claude", SRC, "Spanish")
    assert res["ok"] and res["mode"] == "translate"
    assert res["units"] == 2
    assert res["structure_ok"] is True and res["structure_issues"] == []
    assert res["lint_ok"] is True
    # both unit headers survive, numbered in order
    assert "## Microlearning 1:" in res["out"] and "## Microlearning 2:" in res["out"]
    # preamble was translated too (one extra pass beyond the two units)
    assert len(prompts) == 3
    assert "Curriculum Rationale" in res["out"]


def test_translate_course_uses_glossary_keep_terms(monkeypatch):
    prompts = []
    monkeypatch.setattr(A, "run_cli", lambda prov, prompt, **k: _echo_cli(prompt, prompts))
    monkeypatch.setattr(A, "load_glossary",
                        lambda b=None: {"preferred": [{"term": "Transfer IQ Pro"}], "banned": []})
    res = A.translate_course("claude", SRC, "Spanish", brand="teletracking")
    assert res["ok"]
    assert all("Transfer IQ Pro" in p for p in prompts)   # keep-verbatim reached every pass


def test_translate_course_localize_mode(monkeypatch):
    monkeypatch.setattr(A, "run_cli", lambda prov, prompt, **k: _echo_cli(prompt))
    monkeypatch.setattr(A, "load_glossary", lambda b=None: {"preferred": [], "banned": []})
    res = A.translate_course("claude", SRC, "en-GB")
    assert res["ok"] and res["mode"] == "localize"
    assert res["target"] == "British English (en-GB)"


def test_translate_course_detects_structure_drift(monkeypatch):
    # a provider that DROPS the knowledge-check slide from unit 1 breaks structure
    def _drop_kc(prov, prompt, **k):
        chunk = _chunk_of(prompt)
        chunk = re.sub(r"\n\*\*Slide 3 — Knowledge Check\*\*.*?(?=\Z)", "\n", chunk, flags=re.S)
        return (True, chunk, "")
    monkeypatch.setattr(A, "run_cli", _drop_kc)
    monkeypatch.setattr(A, "load_glossary", lambda b=None: {"preferred": [], "banned": []})
    res = A.translate_course("claude", SRC, "Spanish")
    assert res["ok"]                       # the pass "succeeded"…
    assert res["structure_ok"] is False    # …but the verify caught the dropped block
    assert any("unit 1" in s for s in res["structure_issues"])


def test_translate_course_reports_cli_failure(monkeypatch):
    monkeypatch.setattr(A, "run_cli", lambda prov, prompt, **k: (False, "", "cli boom"))
    monkeypatch.setattr(A, "load_glossary", lambda b=None: {"preferred": [], "banned": []})
    res = A.translate_course("claude", SRC, "Spanish")
    assert res["ok"] is False and "boom" in res["error"]


def test_translate_course_no_units_errors(monkeypatch):
    monkeypatch.setattr(A, "run_cli", lambda prov, prompt, **k: (True, "x", ""))
    monkeypatch.setattr(A, "load_glossary", lambda b=None: {"preferred": [], "banned": []})
    res = A.translate_course("claude", "just some prose, no units", "Spanish")
    assert res["ok"] is False and "unit" in res["error"]
