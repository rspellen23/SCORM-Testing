"""Drift guard for the "What the generator can build" capability note in the
dashboard (dashboard/index.html, the <details class="capnote"> under the course
generator).

The dashboard is a pipeline UI — the operator never picks blocks; the AI chooses
from the AUTHORING_GUIDE. So this note is the ONLY place the operator learns what
the generator can now produce. The interaction/game/assessment/reflection blocks
shipped across the gamification + reframing + C-tier tracks (dragDrop, wordSearch,
crossword, gameShow, quizBoard, speedStreak, reflection, categorize, sequence,
matching, fillBlank) once existed in the engine but were invisible here. These
guards fail if the note drifts back behind the engine and stops naming a capability
the operator can actually get.
"""
import os

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
HTML = open(os.path.join(REPO, "dashboard", "index.html"), encoding="utf-8").read()


def _capnote():
    # the single capability note under the course generator
    assert 'class="capnote"' in HTML
    body = HTML.split('class="capnote"', 1)[1]
    return body.split("</details>", 1)[0].lower()


def test_review_games_are_surfaced():
    note = _capnote()
    for phrase in ("word search", "crossword", "game show", "quiz board", "speed-streak"):
        assert phrase in note, f"review game missing from capability note: {phrase!r}"


def test_graded_interactions_are_surfaced():
    note = _capnote()
    # the five objective-matched interaction blocks, in operator language
    for phrase in ("categorize", "sequence", "matching pairs",
                   "fill in the blank", "label a diagram"):
        assert phrase in note, f"graded interaction missing from capability note: {phrase!r}"


def test_reflection_is_surfaced_as_non_scored():
    note = _capnote()
    assert "reflection" in note
    # the crux of C7: completion-tracked, self-checked, NOT graded
    assert "self-check" in note or "self check" in note or "model answer" in note
    assert "not scored" in note or "not graded" in note


def test_still_lists_the_core_teaching_blocks():
    # the sync EXPANDED the note; it must not have dropped what was already there
    note = _capnote()
    for phrase in ("flashcards", "accordions", "timeline", "comparison",
                   "infographics", "charts", "animations"):
        assert phrase in note, f"pre-existing block dropped from capability note: {phrase!r}"
