"""gameShow — a spin-the-wheel review game built from multiple-choice questions.

Each authored question becomes one wheel slice; the learner spins to draw one,
answers it, then spins again (partial credit — answered N of M correctly). The
options are shuffled DETERMINISTICALLY at build time (src/gameshow.py) so the
correct-answer index is fixed in the IR and resume is stable. This file covers:
the generator (shuffle determinism, correct-index tracking, dedupe, dropping
under-specified questions), the wheel geometry, the grammar → IR, render data-*
attributes (wheel wedges + per-question radio panels), the empty-block fallback,
schema validity, graded-section objective rollup, and that the block is teachable
to the generator (present in the authoring guide). The pure player scorer +
suspend/resume are pinned in tests/test_player.js.
"""
import os
import tempfile

import md_import
import render
import gameshow
from ir_validate import validate_ir


def _import(md, which=1):
    f = tempfile.NamedTemporaryFile("w", suffix=".md", delete=False, encoding="utf-8")
    f.write(md)
    f.close()
    try:
        return md_import.import_md(f.name, which=which)[0]
    finally:
        os.unlink(f.name)


def _render(ir):
    import brand as brandlib
    d = tempfile.mkdtemp()
    render.render_course(ir, os.path.join(d, "c"), brand=brandlib.load_brand("_default"))
    return open(os.path.join(d, "c", "index.html"), encoding="utf-8").read()


def _gs(ir):
    return next(b for b in ir["blocks"] if b["type"] == "gameShow")


_MD = """## Microlearning 1: Review

**Slide 1 — Wrap-up**

*GameShow:* prompt: Spin the wheel to review this lesson.
q: Where do active transfer requests appear first?
a: On the dashboard
option: In the archived report
option: In the admin console
q: What should you do when a step stalls?
a: Escalate the request
option: Delete the request
option: Wait for it to expire
:::
"""


# =========================================================== generator

def test_build_makes_one_slice_per_valid_question():
    out = gameshow.build([
        {"q": "Q1", "correct": "A", "distractors": ["B", "C"]},
        {"q": "Q2", "correct": "D", "distractors": ["E"]},
    ])
    assert out["n"] == 2 and len(out["slices"]) == 2
    for sl in out["slices"]:
        # the answer index always points back at the correct option
        assert sl["options"][sl["answer"]] in ("A", "D")


def test_build_shuffle_is_deterministic():
    q = [{"q": "Where?", "correct": "Dashboard", "distractors": ["Archive", "Console", "Inbox"]}]
    assert gameshow.build(q) == gameshow.build(q)          # same input → identical (byte-stable build)


def test_build_answer_index_tracks_the_correct_option():
    sl = gameshow.build([{"q": "Q", "correct": "RIGHT",
                          "distractors": ["w1", "w2", "w3"]}])["slices"][0]
    assert sl["options"][sl["answer"]] == "RIGHT"
    assert set(sl["options"]) == {"RIGHT", "w1", "w2", "w3"}


def test_build_dedupes_distractor_equal_to_correct():
    sl = gameshow.build([{"q": "Q", "correct": "Same", "distractors": ["same", "Other"]}])["slices"][0]
    assert sl["options"].count("Same") == 1               # case-insensitive dupe dropped
    assert "Other" in sl["options"]


def test_build_drops_underspecified_questions():
    out = gameshow.build([
        {"q": "", "correct": "A", "distractors": ["B"]},   # no stem
        {"q": "Q", "correct": "", "distractors": ["B"]},   # no correct answer
        {"q": "Q", "correct": "A", "distractors": []},     # no distractor → not a question
        {"q": "Good", "correct": "A", "distractors": ["B"]},
    ])
    assert out["n"] == 1 and out["slices"][0]["q"] == "Good"


# =========================================================== wheel geometry

def test_wheel_segments_count_and_center_angles():
    segs = gameshow.wheel_segments(4)
    assert len(segs) == 4
    assert [s["mid"] for s in segs] == [45.0, 135.0, 225.0, 315.0]   # slice centres, clockwise from top
    for s in segs:
        assert s["d"].startswith("M") and "A" in s["d"]  # an arc path


def test_wheel_segments_edge_counts():
    assert gameshow.wheel_segments(0) == []
    one = gameshow.wheel_segments(1)
    assert len(one) == 1 and one[0]["mid"] == 0.0        # a single slice is the whole disc


def test_wheel_segments_are_deterministic():
    assert gameshow.wheel_segments(5) == gameshow.wheel_segments(5)


# =========================================================== grammar → IR

def test_grammar_builds_slices_with_options():
    b = _gs(_import(_MD))
    assert b["type"] == "gameShow"
    assert b["prompt"]                                    # header prompt captured
    assert len(b["slices"]) == 2
    for sl in b["slices"]:
        assert len(sl["options"]) == 3
        assert 0 <= sl["answer"] < 3


def test_grammar_correct_answer_survives_shuffle():
    b = _gs(_import(_MD))
    s0 = b["slices"][0]
    assert s0["options"][s0["answer"]] == "On the dashboard"


def test_new_q_line_starts_the_next_slice():
    b = _gs(_import(_MD))
    stems = [sl["q"] for sl in b["slices"]]
    assert "Where do active transfer requests appear first?" in stems
    assert "What should you do when a step stalls?" in stems


def test_unclosed_block_stops_at_the_next_slide_marker():
    md = _MD.replace(":::\n", "")   # drop the closing fence
    md += "\n**Slide 2 — Next**\n\nPlain body.\n"
    ir = _import(md)
    b = _gs(ir)
    assert b["slices"]
    assert any(x["type"] == "paragraph" and "Plain body" in x.get("html", "") for x in ir["blocks"])


# =========================================================== render

def test_render_emits_wheel_panels_and_feedback():
    b = _gs(_import(_MD))
    html = render.render_block(b)
    assert "data-gameshow" in html
    n = len(b["slices"])
    assert html.count("nv-gs-seg ") == n or html.count('class="nv-gs-seg"') == n   # one wedge per slice
    assert html.count('class="nv-gs-panel"') == n
    # every option is a radio; the correct index rides the panel
    total_opts = sum(len(sl["options"]) for sl in b["slices"])
    assert html.count('type="radio"') == total_opts
    for sl in b["slices"]:
        assert f'data-answer="{sl["answer"]}"' in html
    assert "nv-gs-spin" in html and "data-fb-correct" in html


def test_render_empty_block_is_inert():
    # a gameShow whose questions were all dropped must NOT emit data-gameshow (unanswerable → would stick completion)
    b = {"type": "gameShow", "slices": []}
    html = render.render_block(b)
    assert "data-gameshow" not in html
    assert "nv-gs-empty" in html


def test_render_in_full_course():
    html = _render(_import(_MD))
    assert "data-gameshow" in html and "nv-gs-wheel" in html


# =========================================================== schema + grading

def test_schema_valid():
    validate_ir(_import(_MD), label="gameShow")


_GRADED = """*Graded:* pass 80

## Microlearning 1: Review

**Slide 1 — Quiz**

*Section:* blue · Review · quiz
*GameShow:*
q: Q1
a: A
option: B
option: C
q: Q2
a: D
option: E
option: F
:::
*Section:* blue
"""


def test_graded_section_tags_the_gameshow_objective():
    ir = _import(_GRADED)
    b = _gs(ir)
    assert b.get("objective") == "review"
    assert [o["id"] for o in ir.get("objectives", [])] == ["review"]
    assert 'data-obj="review"' in render.render_block(b)


def test_inline_gameshow_is_not_graded():
    b = _gs(_import(_MD))
    assert "objective" not in b


# =========================================================== authoring-generable

def test_block_is_taught_to_the_generator():
    guide = open(os.path.join(os.path.dirname(__file__), "..", "templates", "AUTHORING_GUIDE.md"),
                 encoding="utf-8").read()
    assert "*GameShow:*" in guide
    assert "q:" in guide and "option:" in guide
