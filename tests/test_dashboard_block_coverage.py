"""Dashboard-sync drift guard — the '6th wiring site'.

`tests/test_block_registry.py` forces every block type to be wired at the four
*engine* sites (schema / renderer / pptx / parser). But nothing forced a new
authorable capability to be *surfaced to the operator* in the dashboard, so the
UI drifted behind the engine (the interaction/game/assessment blocks shipped
invisible until a hand-written sync pass caught up).

This test closes that loop. `dashboard/index.html` carries one operator-facing
"What the generator can build" capability note (`<details class="capnote">`).
Every markdown-authorable block MUST be accounted for as exactly one of:

    * SURFACED   — advertised in the capnote; the mapped phrase must appear there.
    * NOT_SURFACED — a deliberate decision NOT to headline it (basic text /
                     structural markers / media embeds / presentation sugar).

The KEYS are re-derived from `blocks.authorable_types()`, so adding a new
authorable block with no surfacing decision fails CI — the operator UI can no
longer silently fall behind the engine. Course-level directives (`*Points:*`,
`*Celebrate:*`) and CLI tools are intentionally out of scope here: this guard
covers the block registry only (mirrors `test_block_registry`).
"""
import os
import re

import blocks

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
INDEX = os.path.join(ROOT, "dashboard", "index.html")


# --- SURFACED: authorable block -> a phrase that must appear in the capnote ---
# The phrase is the human wording the operator actually reads (the capnote uses
# friendly names, not raw type ids). Several blocks legitimately share one phrase
# (e.g. image / imageText -> "images").
SURFACED = {
    "note":           "callouts",
    "image":          "images",
    "imageText":      "images",
    "flashcard":      "flashcards",
    "accordion":      "accordions",
    "process":        "process",
    "timeline":       "timeline",
    "comparison":     "comparison",
    "infographic":    "infographics",
    "chart":          "charts",
    "knowledgeCheck": "knowledge checks",
    "categorize":     "categorize",
    "sequence":       "sequence",
    "matching":       "matching pairs",
    "fillBlank":      "fill in the blank",
    "dragDrop":       "drag-and-drop",
    "questionBank":   "randomized question bank",
    "scenario":       "decision scenario",
    "reflection":     "reflection",
    "wordSearch":     "word search",
    "crossword":      "crossword",
    "gameShow":       "game show",
    "quizBoard":      "quiz board",
    "speedStreak":    "speed-streak",
}

# --- NOT_SURFACED: authorable blocks deliberately NOT headlined as capabilities.
# basic text / list / table, structural + section markers, the progressive-reveal
# gate, auto-generated objectives, media embeds, and presentation sugar (CTA
# button, card grid, pull-quote). A new block does NOT belong here by default:
# put it in SURFACED unless there's a reason not to advertise it.
NOT_SURFACED = {
    "heading", "paragraph", "statement", "list", "table",
    "divider", "transition", "sectionStart", "sectionEnd",
    "continue", "objectives",
    "video", "audio", "embed",
    "button", "cardGrid", "quote",
}


def _capnote():
    """The text inside the operator's `<details class="capnote">` note."""
    with open(INDEX, encoding="utf-8") as fh:
        html = fh.read()
    m = re.search(r'<details class="capnote">(.*?)</details>', html, re.S)
    assert m, "the capability note (<details class=\"capnote\">) is missing"
    return m.group(1)


def test_every_authorable_block_has_a_surfacing_decision():
    """No authorable block may be left un-bucketed — the drift the guard closes."""
    authorable = blocks.authorable_types()
    accounted = set(SURFACED) | NOT_SURFACED

    unaccounted = authorable - accounted
    assert not unaccounted, (
        f"authorable blocks with NO dashboard-surfacing decision: {sorted(unaccounted)} "
        f"— add each to SURFACED (and to the capnote in dashboard/index.html) or, "
        f"if it should not be advertised, to NOT_SURFACED."
    )


def test_no_stale_or_double_bucketed_entries():
    """The two buckets must reference only real authorable types, disjointly."""
    authorable = blocks.authorable_types()

    overlap = set(SURFACED) & NOT_SURFACED
    assert not overlap, f"blocks in BOTH buckets: {sorted(overlap)}"

    stale = (set(SURFACED) | NOT_SURFACED) - authorable
    assert not stale, (
        f"surfacing buckets reference non-authorable / removed types: {sorted(stale)}"
    )


def test_surfaced_blocks_appear_in_the_capnote():
    """Each advertised block's phrase must actually be present in the capnote."""
    note = _capnote().lower()
    missing = sorted(
        t for t, phrase in SURFACED.items() if phrase.lower() not in note
    )
    assert not missing, (
        f"these blocks are marked SURFACED but their phrase is absent from the "
        f"capability note: {[(t, SURFACED[t]) for t in missing]}"
    )


def test_the_previously_drifted_blocks_are_now_surfaced():
    """Regression pin: questionBank + scenario were the drift this guard exposed."""
    note = _capnote().lower()
    assert "randomized question bank" in note
    assert "decision scenario" in note
