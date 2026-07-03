"""quizBoard — a Jeopardy-style category board built from multiple-choice questions.

Questions are grouped into named categories (columns); each becomes a tile worth
an escalating point value down its column. The learner picks any tile, answers its
MCQ, and the tile flips correct/incorrect (WEIGHTED partial credit — points earned
/ points possible). The options are shuffled DETERMINISTICALLY at build time
(src/quizboard.py, reusing src/gameshow.py) so the correct-answer index is fixed in
the IR and resume is stable. This file covers: the generator (value escalation,
dropping under-specified questions, dropping empty columns, determinism), the
grammar → IR, render data-* attributes (the grid + per-tile radio panels, ragged
columns), the empty-block fallback, schema validity, graded-section objective
rollup, and that the block is teachable to the generator (present in the authoring
guide). The pure player scorer + suspend/resume are pinned in tests/test_player.js.
"""
import os
import tempfile

import md_import
import render
import quizboard
from ir_validate import validate_ir


def _import(md, which=1):
    f = tempfile.NamedTemporaryFile("w", suffix=".md", delete=False, encoding="utf-8")
    f.write(md)
    f.close()
    try:
        return md_import.import_md(f.name, which=which)[0]
    finally:
        os.unlink(f.name)


def _qb(ir):
    return next(b for b in ir["blocks"] if b["type"] == "quizBoard")


_MD = """## Microlearning 1: Review

**Slide 1 — Wrap-up**

*QuizBoard:* prompt: Pick a tile to review this lesson.
category: Queues
q: Where do active transfer requests appear first?
a: On the dashboard
option: In the archived report
option: In the admin console
q: What should you do when a step stalls?
a: Escalate the request
option: Delete the request
category: Roles
q: Who approves an urgent transfer?
a: The charge nurse
option: Any visitor
:::
"""


# =========================================================== generator

def _q(stem, correct, *distractors):
    return {"q": stem, "correct": correct, "distractors": list(distractors)}


def test_build_one_tile_per_valid_question_with_shape():
    out = quizboard.build([
        {"name": "A", "questions": [_q("q1", "c1", "d1"), _q("q2", "c2", "d2")]},
        {"name": "B", "questions": [_q("q3", "c3", "d3")]},
    ])
    assert out["cols"] == 2 and out["rows"] == 2
    names = [c["name"] for c in out["board"]]
    assert names == ["A", "B"]
    assert [len(c["tiles"]) for c in out["board"]] == [2, 1]


def test_build_values_escalate_by_row():
    out = quizboard.build([{"name": "A", "questions": [
        _q("q1", "c1", "d1"), _q("q2", "c2", "d2"), _q("q3", "c3", "d3")]}])
    assert [t["value"] for t in out["board"][0]["tiles"]] == [100, 200, 300]


def test_build_custom_step():
    out = quizboard.build([{"name": "A", "questions": [_q("q1", "c1", "d1"), _q("q2", "c2", "d2")]}], step=200)
    assert [t["value"] for t in out["board"][0]["tiles"]] == [200, 400]


def test_build_answer_index_tracks_the_correct_option():
    out = quizboard.build([{"name": "A", "questions": [_q("stem", "RIGHT", "w1", "w2")]}])
    tile = out["board"][0]["tiles"][0]
    assert tile["options"][tile["answer"]] == "RIGHT"
    assert sorted(tile["options"]) == sorted(["RIGHT", "w1", "w2"])


def test_build_drops_underspecified_and_reflows_values():
    # the 2nd question has no distractor → dropped; the survivors keep contiguous 100/200 values
    out = quizboard.build([{"name": "A", "questions": [
        _q("q1", "c1", "d1"), _q("q2", "c2"), _q("q3", "c3", "d3")]}])
    tiles = out["board"][0]["tiles"]
    assert len(tiles) == 2
    assert [t["value"] for t in tiles] == [100, 200]
    assert [t["q"] for t in tiles] == ["q1", "q3"]


def test_build_drops_empty_category():
    out = quizboard.build([
        {"name": "Good", "questions": [_q("q1", "c1", "d1")]},
        {"name": "Empty", "questions": [_q("q2", "c2")]},   # no distractor → all dropped → column dropped
    ])
    assert [c["name"] for c in out["board"]] == ["Good"]
    assert out["cols"] == 1


def test_build_all_empty_is_inert():
    out = quizboard.build([{"name": "X", "questions": [_q("q", "c")]}])
    assert out == {"board": [], "cols": 0, "rows": 0}


def test_build_is_deterministic():
    cats = [{"name": "A", "questions": [_q("q1", "c1", "d1", "d2"), _q("q2", "c2", "d3", "d4")]}]
    assert quizboard.build(cats) == quizboard.build(cats)


# =========================================================== grammar → IR

def test_grammar_builds_board_with_values():
    b = _qb(_import(_MD))
    assert b["prompt"] == "Pick a tile to review this lesson."
    assert b["cols"] == 2 and b["rows"] == 2
    assert [c["name"] for c in b["board"]] == ["Queues", "Roles"]
    assert [t["value"] for t in b["board"][0]["tiles"]] == [100, 200]
    assert [t["value"] for t in b["board"][1]["tiles"]] == [100]


def test_grammar_correct_answer_survives_shuffle():
    b = _qb(_import(_MD))
    t0 = b["board"][0]["tiles"][0]
    assert t0["options"][t0["answer"]] == "On the dashboard"


def test_new_category_starts_the_next_column():
    b = _qb(_import(_MD))
    assert len(b["board"]) == 2
    assert b["board"][1]["name"] == "Roles"


def test_question_before_any_category_is_ignored():
    md = ("## Microlearning 1: X\n\n**Slide 1 — S**\n\n"
          "*QuizBoard:*\n"
          "q: stray question with no category\n"
          "a: A\n"
          "option: B\n"
          "category: Real\n"
          "q: real question\n"
          "a: C\n"
          "option: D\n"
          ":::\n")
    b = _qb(_import(md))
    assert [c["name"] for c in b["board"]] == ["Real"]
    assert len(b["board"][0]["tiles"]) == 1


def test_unclosed_block_stops_at_the_next_slide_marker():
    md = ("## Microlearning 1: X\n\n**Slide 1 — S**\n\n"
          "*QuizBoard:*\n"
          "category: A\n"
          "q: q1\n"
          "a: c1\n"
          "option: d1\n"
          "**Slide 2 — Next**\n"
          "Body text.\n")
    ir = _import(md)
    b = _qb(ir)
    assert len(b["board"]) == 1 and len(b["board"][0]["tiles"]) == 1
    # the next slide's body survived (the unclosed block didn't swallow it)
    assert any(x["type"] == "paragraph" for x in ir["blocks"])


# =========================================================== render

def test_render_emits_grid_tiles_and_panels():
    b = _qb(_import(_MD))
    html = render.render_block(b)
    assert "data-quizboard" in html
    assert 'style="--qb-cols:2"' in html
    assert html.count("nv-qb-tile") == 3          # 2 + 1 tiles
    assert 'data-value="200"' in html
    assert html.count('class="nv-qb-panel"') == 3
    # ragged column → one blank cell (Roles has no row-2 tile)
    assert "nv-qb-blank" in html


def test_render_panel_carries_answer_and_value():
    b = _qb(_import(_MD))
    html = render.render_block(b)
    # each panel exposes the correct-option index and its point value for the player scorer
    assert 'data-answer=' in html
    assert 'data-value="100"' in html


def test_render_empty_block_is_inert():
    b = {"type": "quizBoard", "board": [], "cols": 0, "rows": 0}
    html = render.render_block(b)
    assert "data-quizboard" not in html
    assert "nv-qb-empty" in html


def test_render_in_full_course():
    ir = _import(_MD)
    import brand as brandlib
    d = tempfile.mkdtemp()
    render.render_course(ir, os.path.join(d, "c"), brand=brandlib.load_brand("_default"))
    html = open(os.path.join(d, "c", "index.html"), encoding="utf-8").read()
    assert "data-quizboard" in html


# =========================================================== schema + grading

def test_schema_valid():
    validate_ir(_import(_MD), label="quizBoard")


_GRADED = """*Graded:* pass 80

## Microlearning 1: Review

**Slide 1 — Quiz**

*Section:* blue · Review · quiz
*QuizBoard:*
category: A
q: Q1
a: A
option: B
option: C
q: Q2
a: D
option: E
:::
*Section:* blue
"""


def test_graded_section_tags_the_quizboard_objective():
    ir = _import(_GRADED)
    b = _qb(ir)
    assert b.get("objective") == "review"
    assert [o["id"] for o in ir.get("objectives", [])] == ["review"]
    assert 'data-obj="review"' in render.render_block(b)


def test_inline_quizboard_is_not_graded():
    b = _qb(_import(_MD))
    assert "objective" not in b


# =========================================================== authoring-generable

def test_block_is_taught_to_the_generator():
    guide = open(os.path.join(os.path.dirname(__file__), "..", "templates", "AUTHORING_GUIDE.md"),
                 encoding="utf-8").read()
    assert "*QuizBoard:*" in guide
    assert "category:" in guide and "option:" in guide
