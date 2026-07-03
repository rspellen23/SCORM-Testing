"""crossword — an interlocking numbered crossword built from clue/answer pairs.

The layout is GENERATED at build time (src/crossword.py) from the authored
answers, so a course builds deterministically. This file covers: the generator
(interlocking validity, crossing, numbering, determinism, cleaning), the grammar
→ IR, render data-* attributes (grid inputs + numbered across/down clue lists),
schema validity, graded-section objective rollup, and that the block is teachable
to the generator (present in the authoring guide). The pure player scorer +
suspend/resume are pinned in tests/test_player.js.
"""
import os
import tempfile

import md_import
import render
import crossword
import brand as brandlib
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
    d = tempfile.mkdtemp()
    render.render_course(ir, os.path.join(d, "c"), brand=brandlib.load_brand("_default"))
    return open(os.path.join(d, "c", "index.html"), encoding="utf-8").read()


def _cw(ir):
    return next(b for b in ir["blocks"] if b["type"] == "crossword")


def _spells(grid, w):
    dr, dc = (1, 0) if w["dir"] == "down" else (0, 1)
    return "".join(grid[w["r"] + dr * k][w["c"] + dc * k] for k in range(len(w["text"])))


# =========================================================== the generator

def test_every_placed_word_reads_correctly_off_the_grid():
    p = crossword.generate(["DASHBOARD", "ESCALATE", "HANDOFF", "TRANSFER"])
    assert p["words"], "at least some words should place"
    for w in p["words"]:
        assert w["dir"] in ("across", "down")
        assert _spells(p["grid"], w) == w["text"]
    # rectangular grid; blocked cells are None
    assert len(p["grid"]) == p["rows"]
    assert all(len(row) == p["cols"] for row in p["grid"])
    assert any(ch is None for row in p["grid"] for ch in row) or p["rows"] * p["cols"] == sum(len(w["text"]) for w in p["words"])


def test_words_interlock_every_non_first_word_crosses():
    # A real crossword: every word after the first shares a cell with an earlier word.
    p = crossword.generate(["DASHBOARD", "ESCALATE", "HANDOFF", "TRANSFER", "ASSIGN"])
    occupied = {}
    for idx, w in enumerate(p["words"]):
        dr, dc = (1, 0) if w["dir"] == "down" else (0, 1)
        cells = [(w["r"] + dr * k, w["c"] + dc * k) for k in range(len(w["text"]))]
        if idx > 0:
            assert any(c in occupied for c in cells), f"{w['text']} does not cross an earlier word"
        for c in cells:
            occupied[c] = w["text"]
    assert len(p["words"]) >= 4   # these interlock well


def test_numbering_is_row_major_and_shared_at_shared_starts():
    p = crossword.generate(["DASHBOARD", "ESCALATE", "HANDOFF", "TRANSFER"])
    # every placed word has a positive number; numbers increase with row-major start order
    starts = sorted(((w["r"], w["c"], w["num"]) for w in p["words"]))
    nums_in_order = [n for _r, _c, n in starts]
    assert all(n > 0 for n in nums_in_order)
    assert nums_in_order == sorted(nums_in_order)
    # a cell that starts both an across and a down word shares ONE number
    by_start = {}
    for w in p["words"]:
        by_start.setdefault((w["r"], w["c"]), set()).add(w["num"])
    assert all(len(v) == 1 for v in by_start.values())


def test_generation_is_deterministic():
    a = crossword.generate(["ALPHA", "BRAVO", "CHARLIE", "DELTA", "ECHO"])
    b = crossword.generate(["ALPHA", "BRAVO", "CHARLIE", "DELTA", "ECHO"])
    assert a["grid"] == b["grid"] and a["words"] == b["words"]
    assert a["rows"] == b["rows"] and a["cols"] == b["cols"]


def test_cleaning_dedupe_and_short_words_dropped():
    p = crossword.generate(["Bed Board", "bed board", "a", "TRANSFER"])
    texts = [w["text"] for w in p["words"]]
    assert "BEDBOARD" in texts and "TRANSFER" in texts
    assert texts.count("BEDBOARD") == 1        # dupe collapsed
    assert all(len(t) >= 2 for t in texts)      # 1-letter dropped


def test_placed_words_kept_in_authored_order():
    p = crossword.generate(["TRANSFER", "ESCALATE", "HANDOFF"])
    order = [w["text"] for w in p["words"]]
    assert order == sorted(order, key=lambda t: ["TRANSFER", "ESCALATE", "HANDOFF"].index(t))


def test_empty_input_is_safe():
    p = crossword.generate(["a", "", "!"])
    assert p == {"grid": [], "words": [], "rows": 0, "cols": 0}


def test_single_word_lays_across_at_origin():
    p = crossword.generate(["HANDOFF"])
    assert len(p["words"]) == 1
    w = p["words"][0]
    assert w == {"text": "HANDOFF", "r": 0, "c": 0, "dir": "across", "num": 1}
    assert p["rows"] == 1 and p["cols"] == len("HANDOFF")


# =========================================================== grammar → IR

_MD = """## Microlearning 1: Terms

**Slide 1 — Vocabulary**

*Crossword:* prompt: Solve the clues.
word: DASHBOARD | Where active items appear
word: ESCALATE
word: Hand Off | Pass responsibility along
word: TRANSFER | Move a patient between units
:::
"""


def test_grammar_builds_a_grid_and_clue_list():
    b = _cw(_import(_MD))
    assert b["type"] == "crossword"
    assert b["prompt"]                                   # header prompt captured
    assert b["rows"] and b["cols"]
    assert len(b["grid"]) == b["rows"]
    assert b["words"]
    for w in b["words"]:
        assert w["dir"] in ("across", "down") and w["num"] > 0


def test_clue_and_display_preserved():
    b = _cw(_import(_MD))
    dash = next((w for w in b["words"] if w["text"] == "DASHBOARD"), None)
    if dash:
        assert "active items" in dash["clue"]
    handoff = next((w for w in b["words"] if w["text"] == "HANDOFF"), None)
    if handoff:
        assert handoff.get("display") == "Hand Off"     # multi-word original kept for the clue heading


def test_unclosed_block_stops_at_the_next_slide_marker():
    md = _MD.replace(":::\n", "")   # drop the closing fence
    md += "\n**Slide 2 — Next**\n\nPlain body.\n"
    ir = _import(md)
    b = _cw(ir)
    assert b["words"]
    # the following slide's paragraph must NOT have been swallowed into the block
    assert any(x["type"] == "paragraph" and "Plain body" in x.get("html", "") for x in ir["blocks"])


# =========================================================== render

def test_render_emits_grid_inputs_numbered_clues_and_feedback():
    b = _cw(_import(_MD))
    html = render.render_block(b)
    assert "data-crossword" in html
    # one input per white cell = total letters minus the shared crossing cells
    white = sum(1 for row in b["grid"] for ch in row if ch is not None)
    assert html.count("nv-cw-input") == white
    assert html.count("nv-cw-block") == b["rows"] * b["cols"] - white
    # each placed word contributes exactly one clue <li> with its answer + spanned cells
    assert html.count('class="nv-cw-clue"') == len(b["words"])
    for w in b["words"]:
        assert f'data-answer="{w["text"]}"' in html
    assert 'data-dir="across"' in html or 'data-dir="down"' in html
    assert "data-cells=" in html
    assert "nv-cw-check" in html and "data-fb-correct" in html
    assert f"--cw-cols:{b['cols']}" in html


def test_render_clue_cells_match_the_word_placement():
    b = _cw(_import(_MD))
    html = render.render_block(b)
    w = b["words"][0]
    dr, dc = (1, 0) if w["dir"] == "down" else (0, 1)
    expect = " ".join(f'{w["r"] + dr * k},{w["c"] + dc * k}' for k in range(len(w["text"])))
    assert f'data-cells="{expect}"' in html


def test_render_in_full_course():
    html = _render(_import(_MD))
    assert "data-crossword" in html and "nv-cw-grid" in html


# =========================================================== schema + grading

def test_schema_valid():
    validate_ir(_import(_MD), label="crossword")


_GRADED = """*Graded:* pass 80

## Microlearning 1: Terms

**Slide 1 — Vocabulary**

*Section:* blue · Key Terms · quiz
*Crossword:*
word: DASHBOARD | a
word: ESCALATE | b
word: HANDOFF | c
:::
*Section:* blue
"""


def test_graded_section_tags_the_crossword_objective():
    ir = _import(_GRADED)
    b = _cw(ir)
    assert b.get("objective") == "key-terms"
    assert [o["id"] for o in ir.get("objectives", [])] == ["key-terms"]
    # render surfaces the subscore hook the player reads
    assert 'data-obj="key-terms"' in render.render_block(b)


def test_inline_crossword_is_not_graded():
    b = _cw(_import(_MD))                                 # no graded section
    assert "objective" not in b


# =========================================================== authoring-generable

def test_block_is_taught_to_the_generator():
    # the whole point of this item: the LLM must be able to EMIT it with the course.
    guide = open(os.path.join(os.path.dirname(__file__), "..", "templates", "AUTHORING_GUIDE.md"),
                 encoding="utf-8").read()
    assert "*Crossword:*" in guide
    assert "word:" in guide
