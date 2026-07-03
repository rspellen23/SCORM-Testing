"""M12→M13 follow-up — matching/sequencing/fill-in-the-blank count toward the graded aggregate.

The three M12 partial-credit blocks now roll into a graded *Section:*'s subscore exactly like a
knowledge check, but contribute FRACTIONAL {got,max} credit (per-sub-item points). This file
covers the md_import tagging + render `data-obj` emission; the player-side fractional aggregate
math is pinned in tests/test_player.js (node --test).

Two locked design rules (James, 2026-07-01):
  • per-sub-item points — a 3-pair match weighs 3× a single MCQ (tested in test_player.js);
  • SECTION-TAGGED ONLY — a block counts ONLY inside a graded *Section:*; an inline block stays
    formative and a graded course with NO graded sections never pulls M12 blocks into a fallback.
"""
import os
import tempfile

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


def _render(ir):
    d = tempfile.mkdtemp()
    render.render_course(ir, os.path.join(d, "c"), brand=brandlib.load_brand("_default"))
    return open(os.path.join(d, "c", "index.html"), encoding="utf-8").read()


def _block(ir, t):
    return next(b for b in ir["blocks"] if b["type"] == t)


# A graded course; each M12 block wrapped in its own graded section band.
_GRADED_M12 = """# Course

*Graded:* pass 80

## Microlearning 1: Unit

**Slide 1 — Matching**
*Section:* blue · Terminology · pass 70
*Matching:* prompt: Match each term.
pair: Alpha -> First
pair: Beta -> Second
pair: Gamma -> Third
:::
*Section:* end

**Slide 2 — Sequence**
*Section:* gold · Ordering · pass 60
*Sequence:* prompt: Order the steps.
step: One
step: Two
:::
*Section:* end

**Slide 3 — Fill**
*Section:* teal · Vocabulary
*FillBlank:* prompt: Complete it.
blank: The sky is ___ -> blue
:::
*Section:* end
"""


def test_matching_in_graded_section_is_tagged_and_registered():
    ir = _import(_GRADED_M12)[0]
    b = _block(ir, "matching")
    assert b["objective"] == "terminology"
    obj = next(o for o in ir["objectives"] if o["id"] == "terminology")
    assert obj == {"id": "terminology", "name": "Terminology", "pass": 70}


def test_sequence_in_graded_section_is_tagged_and_registered():
    ir = _import(_GRADED_M12)[0]
    b = _block(ir, "sequence")
    assert b["objective"] == "ordering"
    obj = next(o for o in ir["objectives"] if o["id"] == "ordering")
    assert obj == {"id": "ordering", "name": "Ordering", "pass": 60}


def test_fillblank_in_graded_section_is_tagged_and_registered():
    ir = _import(_GRADED_M12)[0]
    b = _block(ir, "fillBlank")
    assert b["objective"] == "vocabulary"
    obj = next(o for o in ir["objectives"] if o["id"] == "vocabulary")
    # No `pass` threshold declared → null (report-only, still gates on overall pass mark).
    assert obj == {"id": "vocabulary", "name": "Vocabulary", "pass": None}


def test_all_three_objectives_present_and_ordered():
    ir = _import(_GRADED_M12)[0]
    assert [o["id"] for o in ir["objectives"]] == ["terminology", "ordering", "vocabulary"]
    validate_ir(ir, label="graded-m12")


def test_kc_and_m12_share_one_objective_by_name():
    # A KC and a matching block in identically-named sections merge into ONE subscore.
    md = """# Course

*Graded:* pass 80

## Microlearning 1: Unit

**Slide 1 — Knowledge Check**
*Section:* blue · Safety · pass 75
*Question:* A safety question?
- A) Right
- B) Wrong
*Correct Answer:* A

**Slide 2 — Matching**
*Section:* blue · Safety · pass 75
*Matching:* prompt: Match.
pair: Alpha -> First
pair: Beta -> Second
:::
*Section:* end
"""
    ir = _import(md)[0]
    assert [o["id"] for o in ir["objectives"]] == ["safety"]      # deduped, not two
    assert _block(ir, "knowledgeCheck")["objective"] == "safety"
    assert _block(ir, "matching")["objective"] == "safety"


def test_inline_m12_block_stays_formative():
    # No *Section:* → no objective tag, no objective registered (section-tagged only).
    md = """# Course

*Graded:* pass 80

## Microlearning 1: Unit

**Slide 1 — Matching**
*Matching:* prompt: Match.
pair: Alpha -> First
pair: Beta -> Second
:::
"""
    ir = _import(md)[0]
    assert "objective" not in _block(ir, "matching")
    assert ir["objectives"] == []


def test_graded_course_no_sections_never_pulls_m12_into_fallback():
    # A graded course whose ONLY interactive block is an untagged matching block: the M13
    # KC-fallback (count everything when there are no objectives) must NOT sweep it in.
    md = """# Course

*Graded:* pass 80

## Microlearning 1: Unit

**Slide 1 — Matching**
*Matching:* prompt: Match.
pair: Alpha -> First
:::
"""
    ir = _import(md)[0]
    assert ir["objectives"] == []
    assert "objective" not in _block(ir, "matching")


def test_named_section_in_ungraded_course_leaves_m12_untagged():
    # Same authored section, but the course is NOT graded → the section is inert (mirrors KCs).
    md = """# Course

## Microlearning 1: Unit

**Slide 1 — Matching**
*Section:* blue · Terminology · pass 70
*Matching:* prompt: Match.
pair: Alpha -> First
:::
*Section:* end
"""
    ir = _import(md)[0]
    assert ir["graded"] is False
    assert "objective" not in _block(ir, "matching")
    assert ir["objectives"] == []


def test_m12_only_graded_course_is_gradeable_end_to_end():
    # A graded "quiz" made ENTIRELY of matching questions (no KCs): objectives register and
    # the body carries data-objectives, so the player's completion gate has a summative score
    # to act on even though kcs.length is 0 (the OBJECTIVES.length disjunct in maybeComplete).
    md = """# Course

*Graded:* pass 70

## Microlearning 1: Unit

**Slide 1 — Matching**
*Section:* blue · Terminology · pass 70
*Matching:* prompt: Match.
pair: Alpha -> First
pair: Beta -> Second
:::
*Section:* end
"""
    ir = _import(md)[0]
    assert ir["graded"] is True
    assert not any(b["type"] == "knowledgeCheck" for b in ir["blocks"])   # no KCs at all
    assert [o["id"] for o in ir["objectives"]] == ["terminology"]
    html = _render(ir)
    assert 'data-graded="1"' in html
    assert 'data-objectives=' in html            # OBJECTIVES non-empty client-side → gate engages
    assert 'data-obj="terminology"' in html


def test_render_emits_data_obj_only_on_tagged_block():
    tagged = _render(_import(_GRADED_M12)[0])
    assert 'data-match data-obj="terminology"' in tagged
    assert 'data-seq data-obj="ordering"' in tagged
    assert 'data-fill data-obj="vocabulary"' in tagged

    md_inline = """# Course

*Graded:* pass 80

## Microlearning 1: Unit

**Slide 1 — Matching**
*Matching:* prompt: Match.
pair: Alpha -> First
:::
"""
    html = _render(_import(md_inline)[0])
    assert "data-match" in html
    assert "data-obj=" not in html   # untagged block carries no objective attribute
