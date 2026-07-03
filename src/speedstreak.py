"""Speed-streak review game (build-time, pure Python).

A fast, one-at-a-time MCQ run: the LLM (or an operator) supplies a list of
multiple-choice questions; the learner answers them in sequence, building a
CONSECUTIVE-CORRECT streak. An optional per-question countdown adds time
pressure — but the timer only drives a COSMETIC speed bonus + combo score;
correctness and the graded {got,max} never have a time limit. That keeps the
block fully accessible (no WCAG 2.2.1 "timing adjustable" problem — the essential
function has no time limit) and grades deterministically. The streak/combo
multiplier is likewise a motivational display, never part of the grade (mirrors
the points/XP overlay decision).

Like src/gameshow.py / src/quizboard.py this runs at course-BUILD time (called
from md_import): the whole run lives in the IR so the build is self-contained and
deterministic. The hard part — normalising each question and DETERMINISTICALLY
shuffling its options so the correct-option index is fixed and resume-stable — is
REUSED verbatim from gameshow.build() (same seeded LCG, no wall-clock), so the
game blocks can't drift apart. This module only adds the flat run shape and the
optional timer on top.
"""
import gameshow


def build(questions, *, timer=0):
    """Normalise `questions` into an ordered run of MCQ rounds.

    `questions` = [{"q": stem, "correct": answer, "distractors": [str, …]}, …]
    (the same shape gameShow takes). Returns
    {"rounds": [{"q", "options": [str, …], "answer": <index>}, …], "n": N,
     "timer": <seconds>}.

    Options are shuffled deterministically via gameshow.build() (a question missing
    its stem / correct answer / every distractor is dropped), so a course builds
    byte-identically and the correct-option index is fixed in the IR. `timer` is the
    optional per-question countdown in whole seconds (0 = untimed); it only drives a
    cosmetic speed bonus at play time, never correctness. A negative or non-numeric
    timer is treated as 0.
    """
    built = gameshow.build(questions)
    try:
        t = int(timer)
    except (TypeError, ValueError):
        t = 0
    if t < 0:
        t = 0
    return {"rounds": built["slices"], "n": built["n"], "timer": t}
