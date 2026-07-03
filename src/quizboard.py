"""Quiz-board (Jeopardy-style) generator (build-time, pure Python).

A category board: the LLM (or an operator) supplies several CATEGORIES, each a
short list of multiple-choice questions ordered easiest-first. Each question
becomes one tile; a tile's POINT VALUE escalates with its row (row 1 lowest, the
bottom row highest — the classic risk/reward board). At play time the learner
picks any tile, answers its MCQ, and the tile flips to reveal correct/incorrect.
Scored with WEIGHTED PARTIAL credit (points earned / points possible), so the
tally naturally reads as a game-show score.

Like src/gameshow.py this runs at course-BUILD time (called from md_import): the
whole board lives in the IR so the build is self-contained and deterministic. The
hard part — normalising each question and DETERMINISTICALLY shuffling its options
so the correct-option index is fixed and resume-stable — is REUSED verbatim from
gameshow.build() (same seeded LCG, no wall-clock), so the two game blocks can't
drift apart. This module only adds the board shape on top: it drops questions the
same way gameshow does, assigns each surviving tile its row value, and drops a
category left with no answerable tiles (an all-blank column is useless).
"""
import gameshow


DEFAULT_VALUE_STEP = 100   # row 1 = 100, row 2 = 200, … (position-derived, per design)


def build(categories, *, step=DEFAULT_VALUE_STEP):
    """Normalise `categories` into a scored board of tiles.

    `categories` = [{"name": str, "questions": [{"q", "correct", "distractors":[…]}, …]}, …].
    Returns {"board": [{"name": str, "tiles": [{"q", "options": [str,…], "answer": <idx>,
    "value": <int>}, …]}, …], "cols": <kept category count>, "rows": <max tiles in any column>}.
    (The IR field is named `board` — `categories` is already taken by the chart block.)

    Each category's questions are run through gameshow.build() (deterministic option
    shuffle + drop of any question missing its stem / correct answer / every distractor),
    so a course builds byte-identically. Surviving tiles are numbered top-down and given
    an escalating value (`(row + 1) * step`) — a dropped question does NOT leave a hole, the
    remaining tiles simply shift up, keeping the column's values contiguous. A category with
    no surviving tiles is dropped entirely.
    """
    out = []
    for cat in categories or []:
        name = (cat.get("name") or "").strip()
        built = gameshow.build(cat.get("questions") or [])
        tiles = []
        for row, sl in enumerate(built.get("slices", [])):
            tiles.append({"q": sl["q"], "options": sl["options"],
                          "answer": sl["answer"], "value": (row + 1) * step})
        if not tiles:                # an all-blank column is useless — drop it
            continue
        out.append({"name": name, "tiles": tiles})
    cols = len(out)
    rows = max((len(c["tiles"]) for c in out), default=0)
    return {"board": out, "cols": cols, "rows": rows}
