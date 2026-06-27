"""Audit item 2.6 — the lint catches malformed interactive blocks, and the
parser hardens what it can (clamp cardGrid columns; loosen the KC option regex).

Each malformed case must fail authoring.lint() with a clear message instead of
shipping a silently broken (unscorable / unanswerable) activity.
"""
import os
import tempfile

import authoring
import md_import

_HEAD = """## Microlearning 1: Lint Test

**Slide 1 — Learning Objectives**
*Visual:* graphic · obj · slot: `obj`
- Learn the thing

**Slide 2 — Check**
"""


def _lint(extra):
    return authoring.lint(_HEAD + extra)


# --- KC option regex loosened: lowercase letters and `.` accepted ------------

def test_kc_accepts_lowercase_and_dot():
    ok, _, errs = _lint("*Question:* Which?\n- a. First\n- b. Second\n*Correct Answer:* b\n")
    assert ok, errs


# --- KC must mark exactly one in-range correct option -----------------------

def test_kc_missing_answer_fails():
    ok, _, errs = _lint("*Question:* Which?\n- A) First\n- B) Second\n")
    assert not ok and any("exactly ONE correct" in e for e in errs), errs


def test_kc_out_of_range_answer_fails():
    ok, _, errs = _lint("*Question:* Which?\n- A) First\n- B) Second\n*Correct Answer:* C\n")
    assert not ok and any("exactly ONE correct" in e for e in errs), errs


def test_kc_fewer_than_two_options_fails():
    ok, _, errs = _lint("*Question:* Which?\n- A) Only one\n*Correct Answer:* A\n")
    assert not ok and any("fewer than 2" in e for e in errs), errs


# --- categorize items must resolve to a real bucket -------------------------

def test_categorize_good_passes():
    ok, _, errs = _lint("*Categorize:*\nbucket: Fruit\nitem: Apple -> Fruit\n")
    assert ok, errs


def test_categorize_typo_bucket_fails():
    ok, _, errs = _lint("*Categorize:*\nbucket: Fruit\nitem: Apple -> Friut\n")
    assert not ok and any("doesn't map to a real bucket" in e for e in errs), errs


# --- cardGrid columns clamp to the schema max (4) ---------------------------

def test_cardgrid_columns_clamped():
    md = (_HEAD + "*Cards:* columns: 9\n::: card\ntitle: A\n:::\n")
    f = tempfile.NamedTemporaryFile("w", suffix=".md", delete=False, encoding="utf-8")
    f.write(md)
    f.close()
    try:
        ir, _ = md_import.import_md(f.name, which=1)
    finally:
        os.unlink(f.name)
    grid = next(b for b in ir["blocks"] if b["type"] == "cardGrid")
    assert grid["columns"] == 4, grid.get("columns")


# --- B1: a multi-scene scenario where a later scene has no choices ----------
# (the old check passed if ANY ONE scene had responses, letting dead-ends through)

_SCEN_HEAD = ("*Scenario:* A patient-flow decision\n"
              "::: scene\n"
              "title: First\n"
              "The unit is full. What do you do?\n"
              "- Escalate to the charge nurse · preferred · feedback: right call\n"
              "- Do nothing\n")


def test_scenario_dead_end_scene_fails_lint():
    extra = _SCEN_HEAD + ("::: scene\n"
                          "title: Second\n"
                          "Now the transfer arrives — but this scene has no choices.\n")
    ok, _, errs = _lint(extra)
    assert not ok and any("dead-end" in e for e in errs), errs


def test_scenario_all_scenes_with_choices_passes():
    extra = _SCEN_HEAD + ("::: scene\n"
                          "title: Second\n"
                          "The transfer arrives.\n"
                          "- Accept it · preferred · feedback: good\n"
                          "- Refuse it\n")
    ok, _, errs = _lint(extra)
    assert ok, errs


# --- B2: an objectives block with no outcome bullets ------------------------

def test_empty_objectives_block_fails_lint():
    # *Objectives:* lead-in with NO `- ` bullets under it
    ok, _, errs = _lint("*Objectives:* By the end you will be able to:\n\nSome prose.\n")
    assert not ok and any("no outcomes" in e for e in errs), errs


def test_objectives_block_with_items_passes():
    ok, _, errs = _lint("*Objectives:* By the end you will be able to:\n"
                        "- Identify the flow bottleneck\n- Escalate correctly\n")
    assert ok, errs
