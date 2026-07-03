"""speedStreak — a fast one-at-a-time MCQ run with a consecutive-correct streak.

The learner answers questions in sequence, building a streak; an optional
per-question countdown adds a COSMETIC speed bonus but never touches correctness
or the graded score (so the block stays accessible and grades deterministically).
The options are shuffled DETERMINISTICALLY at build time (src/speedstreak.py,
reusing src/gameshow.py) so the correct-answer index is fixed in the IR and resume
is stable. This file covers: the generator (reuse of gameshow.build determinism,
correct-index tracking, dropping under-specified questions, timer normalisation),
the grammar → IR (including the `timer:` header option and prompt/timer ordering),
render data-* attributes (per-question radio panels, the timer chip only when
timed, the empty-block fallback), schema validity, graded-section objective rollup,
and that the block is teachable to the generator. The pure player scorer + combo +
suspend/resume are pinned in tests/test_player.js.
"""
import os
import tempfile

import md_import
import render
import speedstreak
from ir_validate import validate_ir


def _import(md, which=1):
    f = tempfile.NamedTemporaryFile("w", suffix=".md", delete=False, encoding="utf-8")
    f.write(md)
    f.close()
    try:
        return md_import.import_md(f.name, which=which)[0]
    finally:
        os.unlink(f.name)


def _ss(ir):
    return next(b for b in ir["blocks"] if b["type"] == "speedStreak")


_MD = """## Microlearning 1: Review

**Slide 1 — Rapid review**

*SpeedStreak:* timer: 15 prompt: How fast can you clear this review?
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

def test_build_makes_one_round_per_valid_question():
    out = speedstreak.build([
        {"q": "Q1", "correct": "A", "distractors": ["B", "C"]},
        {"q": "Q2", "correct": "D", "distractors": ["E"]},
    ])
    assert out["n"] == 2 and len(out["rounds"]) == 2
    for r in out["rounds"]:
        assert r["options"][r["answer"]] in ("A", "D")


def test_build_reuses_gameshow_shuffle_determinism():
    q = [{"q": "Where?", "correct": "Dashboard", "distractors": ["Archive", "Console", "Inbox"]}]
    assert speedstreak.build(q) == speedstreak.build(q)          # byte-stable build
    # the round shape matches gameShow's slice shape (same shuffle under the hood)
    import gameshow
    assert speedstreak.build(q)["rounds"] == gameshow.build(q)["slices"]


def test_build_answer_index_tracks_the_correct_option():
    r = speedstreak.build([{"q": "Q", "correct": "RIGHT",
                            "distractors": ["w1", "w2", "w3"]}])["rounds"][0]
    assert r["options"][r["answer"]] == "RIGHT"
    assert set(r["options"]) == {"RIGHT", "w1", "w2", "w3"}


def test_build_drops_underspecified_questions():
    out = speedstreak.build([
        {"q": "", "correct": "A", "distractors": ["B"]},   # no stem
        {"q": "Q", "correct": "", "distractors": ["B"]},   # no correct answer
        {"q": "Q", "correct": "A", "distractors": []},     # no distractor → not a question
        {"q": "Good", "correct": "A", "distractors": ["B"]},
    ])
    assert out["n"] == 1 and out["rounds"][0]["q"] == "Good"


def test_build_timer_normalises():
    assert speedstreak.build([], timer=20)["timer"] == 20
    assert speedstreak.build([])["timer"] == 0            # default untimed
    assert speedstreak.build([], timer=-5)["timer"] == 0  # negative clamped to 0
    assert speedstreak.build([], timer="oops")["timer"] == 0   # non-numeric → 0


# =========================================================== grammar → IR

def test_grammar_builds_rounds_with_options_and_timer():
    b = _ss(_import(_MD))
    assert b["type"] == "speedStreak"
    assert b["prompt"]                                    # header prompt captured
    assert b["timer"] == 15                               # header timer captured
    assert len(b["rounds"]) == 2
    for r in b["rounds"]:
        assert len(r["options"]) == 3
        assert 0 <= r["answer"] < 3


def test_grammar_prompt_does_not_swallow_a_leading_timer():
    b = _ss(_import(_MD))
    # timer: 15 appears before prompt: on the header — prompt must not contain the timer token
    assert "timer" not in b["prompt"].lower()
    assert b["prompt"].startswith("How fast")


def test_grammar_prompt_first_then_timer_still_parses_both():
    md = _MD.replace("*SpeedStreak:* timer: 15 prompt: How fast can you clear this review?",
                     "*SpeedStreak:* prompt: How fast can you clear this review? timer: 15")
    b = _ss(_import(md))
    assert b["timer"] == 15
    assert "timer" not in b["prompt"].lower()             # trailing timer stripped from the prompt


def test_grammar_untimed_omits_timer_key():
    md = _MD.replace("*SpeedStreak:* timer: 15 prompt: How fast can you clear this review?",
                     "*SpeedStreak:* prompt: Answer these in order.")
    b = _ss(_import(md))
    assert "timer" not in b                               # absent → byte-identical to a plain block


def test_grammar_correct_answer_survives_shuffle():
    b = _ss(_import(_MD))
    r0 = b["rounds"][0]
    assert r0["options"][r0["answer"]] == "On the dashboard"


def test_new_q_line_starts_the_next_round():
    b = _ss(_import(_MD))
    stems = [r["q"] for r in b["rounds"]]
    assert "Where do active transfer requests appear first?" in stems
    assert "What should you do when a step stalls?" in stems


def test_unclosed_block_stops_at_the_next_slide_marker():
    md = _MD.replace(":::\n", "")   # drop the closing fence
    md += "\n**Slide 2 — Next**\n\nPlain body.\n"
    ir = _import(md)
    b = _ss(ir)
    assert b["rounds"]
    assert any(x["type"] == "paragraph" and "Plain body" in x.get("html", "") for x in ir["blocks"])


# =========================================================== render

def test_render_emits_panels_timer_and_feedback():
    b = _ss(_import(_MD))
    html = render.render_block(b)
    assert "data-speedstreak" in html
    assert 'data-timer="15"' in html
    n = len(b["rounds"])
    assert html.count('class="nv-ss-panel"') == n
    total_opts = sum(len(r["options"]) for r in b["rounds"])
    assert html.count('type="radio"') == total_opts
    for r in b["rounds"]:
        assert f'data-answer="{r["answer"]}"' in html
    assert "nv-ss-start" in html and "nv-ss-timer" in html and "data-fb-correct" in html


def test_render_untimed_omits_timer_chip():
    b = {"type": "speedStreak", "rounds": [{"q": "Q", "options": ["A", "B"], "answer": 0}]}
    html = render.render_block(b)
    assert 'data-timer="0"' in html
    assert "nv-ss-timer" not in html          # no timer chip / bar when untimed
    assert "nv-ss-timerbar" not in html


def test_render_empty_block_is_inert():
    # a speedStreak whose questions were all dropped must NOT emit data-speedstreak
    b = {"type": "speedStreak", "rounds": []}
    html = render.render_block(b)
    assert "data-speedstreak" not in html
    assert "nv-ss-empty" in html


def test_render_in_full_course():
    import brand as brandlib
    d = tempfile.mkdtemp()
    render.render_course(_import(_MD), os.path.join(d, "c"), brand=brandlib.load_brand("_default"))
    html = open(os.path.join(d, "c", "index.html"), encoding="utf-8").read()
    assert "data-speedstreak" in html and "nv-ss-panels" in html


# =========================================================== schema + grading

def test_schema_valid():
    validate_ir(_import(_MD), label="speedStreak")


_GRADED = """*Graded:* pass 80

## Microlearning 1: Review

**Slide 1 — Quiz**

*Section:* blue · Review · quiz
*SpeedStreak:*
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


def test_graded_section_tags_the_speedstreak_objective():
    ir = _import(_GRADED)
    b = _ss(ir)
    assert b.get("objective") == "review"
    assert [o["id"] for o in ir.get("objectives", [])] == ["review"]
    assert 'data-obj="review"' in render.render_block(b)


def test_inline_speedstreak_is_not_graded():
    b = _ss(_import(_MD))
    assert "objective" not in b


# =========================================================== authoring-generable

def test_block_is_taught_to_the_generator():
    guide = open(os.path.join(os.path.dirname(__file__), "..", "templates", "AUTHORING_GUIDE.md"),
                 encoding="utf-8").read()
    assert "*SpeedStreak:*" in guide
    assert "q:" in guide and "option:" in guide
    assert "timer:" in guide
