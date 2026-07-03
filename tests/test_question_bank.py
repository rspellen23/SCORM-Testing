"""C5 — question bank + randomization (authoring / IR / render side).

A `*Bank:* draw N` block pools question children (knowledgeCheck + the M12
matching/sequence/fillBlank types); the player draws N at runtime, shuffles KC
options, and persists the drawn set in suspend_data (resume-stable). The player-side
draw/shuffle math is pinned in tests/test_player.js (node --test); this file covers
the grammar → IR, the render `data-bank`/`data-draw` wrapper (whole pool ships), and
graded-section objective inheritance onto the pooled children.

Scope (locked, James 2026-07-01): runtime per-LAUNCH draw + option shuffle + resume-
stable this commit; in-session Retry re-uses the drawn set (re-draw-on-retry is a
follow-up). Banks pool ALL self-scoring question types.
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


_BANK = """# Course

## Microlearning 1: Unit

**Slide 1 — Quiz pool**
*Bank:* draw 2
*Question:* Which is a controlled substance?
- A) Aspirin
- B) Morphine
*Correct Answer:* B
*Question:* Which is over the counter?
- A) Ibuprofen
- B) Fentanyl
*Correct Answer:* A
*Matching:* prompt: Match term to meaning.
pair: Alpha -> First
pair: Beta -> Second
:::
*FillBlank:* prompt: Complete it.
blank: The sky is ___ -> blue
:::
*Bank:* end
"""


def test_bank_parses_pool_and_draw():
    b = _block(_import(_BANK)[0], "questionBank")
    assert b["draw"] == 2
    assert [q["type"] for q in b["questions"]] == [
        "knowledgeCheck", "knowledgeCheck", "matching", "fillBlank"]


def test_bank_children_keep_their_parsed_fields():
    b = _block(_import(_BANK)[0], "questionBank")
    kc = b["questions"][0]
    assert kc["prompt"] == "Which is a controlled substance?"
    assert [o["correct"] for o in kc["options"]] == [False, True]
    assert [(p["left"], p["right"]) for p in b["questions"][2]["pairs"]] == [
        ("Alpha", "First"), ("Beta", "Second")]
    assert b["questions"][3]["blanks"][0]["answers"] == ["blue"]


def test_bank_draw_defaults_to_pool_size():
    md = _BANK.replace("*Bank:* draw 2", "*Bank:*")
    b = _block(_import(md)[0], "questionBank")
    assert b["draw"] == 4          # no `draw N` → draw the whole pool


def test_bank_ir_validates():
    validate_ir(_import(_BANK)[0], label="bank")


def test_bank_closed_by_lone_fence():
    # `:::` closes the bank just like `*Bank:* end`.
    md = _BANK.replace("*Bank:* end", ":::")
    b = _block(_import(md)[0], "questionBank")
    assert len(b["questions"]) == 4


def test_render_ships_whole_pool_with_data_bank_and_draw():
    html = _render(_import(_BANK)[0])
    assert 'data-bank data-draw="2"' in html
    # the WHOLE pool ships (player prunes at runtime): both KCs, the match, the fill.
    assert html.count("nv-kc-prompt") == 2
    assert "data-match" in html and "data-fill" in html
    assert html.count("data-answer=") == 2          # matching pairs


def test_bank_does_not_trip_single_kc_slide_path():
    # A bank body carries *Question:* children; it must NOT be consumed as one slide KC.
    ir = _import(_BANK)[0]
    assert any(b["type"] == "questionBank" for b in ir["blocks"])
    # the inner questions live INSIDE the bank, not as top-level knowledgeCheck blocks
    assert not any(b["type"] == "knowledgeCheck" for b in ir["blocks"])


def test_bank_in_graded_section_tags_every_child():
    md = """# Course

*Graded:* pass 80

## Microlearning 1: Unit

**Slide 1 — Graded pool**
*Section:* blue · Safety · pass 70
*Bank:* draw 1
*Question:* A safety question?
- A) Right
- B) Wrong
*Correct Answer:* A
*Matching:* prompt: Match.
pair: Alpha -> First
:::
*Bank:* end
*Section:* end
"""
    ir = _import(md)[0]
    bank = _block(ir, "questionBank")
    assert bank["objective"] == "safety"
    assert all(q.get("objective") == "safety" for q in bank["questions"])
    # objective registered once
    assert [o["id"] for o in ir["objectives"]] == ["safety"]
    # rendered children carry data-obj so they feed the graded aggregate
    html = _render(ir)
    assert html.count('data-obj="safety"') == 2      # the KC + the matching child


def test_bank_inline_stays_formative():
    # A bank NOT in a graded section → no objective on the bank or its children.
    ir = _import(_BANK)[0]
    bank = _block(ir, "questionBank")
    assert "objective" not in bank
    assert all("objective" not in q for q in bank["questions"])
    assert ir["objectives"] == []
