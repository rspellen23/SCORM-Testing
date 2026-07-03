"""wordSearch — find hidden words in a letter grid, built from a term list.

The letter grid is GENERATED at build time (src/wordsearch.py) from the authored
terms, so a course builds deterministically. This file covers: the generator
(placement validity, determinism, cleaning), the grammar → IR, render data-*
attributes, schema validity, graded-section objective rollup, and that the block
is teachable to the generator (present in the authoring guide). The pure player
scorer + suspend/resume are pinned in tests/test_player.js.
"""
import os
import tempfile

import md_import
import render
import wordsearch
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


def _ws(ir):
    return next(b for b in ir["blocks"] if b["type"] == "wordSearch")


def _spells(grid, w):
    return "".join(grid[w["r"] + w["dr"] * k][w["c"] + w["dc"] * k] for k in range(len(w["text"])))


# =========================================================== the generator

def test_every_word_is_actually_placed_in_the_grid():
    p = wordsearch.generate(["CURSOR", "SUITE", "HANDOFF", "ESCALATE"])
    assert len(p["words"]) == 4
    for w in p["words"]:
        assert _spells(p["grid"], w) == w["text"]
    # square grid at least as wide as the longest word
    assert len(p["grid"]) == p["size"]
    assert all(len(row) == p["size"] for row in p["grid"])
    assert p["size"] >= len("ESCALATE")


def test_generation_is_deterministic():
    a = wordsearch.generate(["ALPHA", "BRAVO", "CHARLIE", "DELTA"])
    b = wordsearch.generate(["ALPHA", "BRAVO", "CHARLIE", "DELTA"])
    assert a["grid"] == b["grid"] and a["words"] == b["words"]


def test_cleaning_dedupe_and_short_words_dropped():
    p = wordsearch.generate(["Bed Board", "bed board", "a", "TIP!"])
    texts = [w["text"] for w in p["words"]]
    assert texts == ["BEDBOARD", "TIP"]        # spaces/punct stripped, dupe + 1-letter dropped
    for w in p["words"]:
        assert _spells(p["grid"], w) == w["text"]


def test_words_preserved_in_authored_order():
    p = wordsearch.generate(["ZEBRA", "OX", "CAT"])   # not longest-first
    assert [w["text"] for w in p["words"]] == ["ZEBRA", "OX", "CAT"]


def test_empty_input_is_safe():
    p = wordsearch.generate(["a", "", "!"])
    assert p == {"grid": [], "words": [], "size": 0}


# =========================================================== grammar → IR

_MD = """## Microlearning 1: Terms

**Slide 1 — Vocabulary**

*WordSearch:* prompt: Find the terms.
term: CURSOR | The blinking screen marker
term: SUITE
term: Bed Board
:::
"""


def test_grammar_builds_a_grid_and_word_list():
    b = _ws(_import(_MD))
    assert b["type"] == "wordSearch"
    assert b["prompt"]                                   # header prompt captured
    texts = [w["text"] for w in b["words"]]
    assert texts == ["CURSOR", "SUITE", "BEDBOARD"]
    assert b["size"] == len(b["grid"]) >= len("BEDBOARD")


def test_clue_and_display_preserved():
    b = _ws(_import(_MD))
    cursor = next(w for w in b["words"] if w["text"] == "CURSOR")
    assert "blinking" in cursor["clue"]
    bedboard = next(w for w in b["words"] if w["text"] == "BEDBOARD")
    assert bedboard.get("display") == "Bed Board"       # multi-word original kept for the list
    suite = next(w for w in b["words"] if w["text"] == "SUITE")
    assert "display" not in suite                        # single word → no redundant display


def test_unclosed_block_stops_at_the_next_slide_marker():
    md = _MD.replace(":::\n", "")   # drop the closing fence
    md += "\n**Slide 2 — Next**\n\nPlain body.\n"
    ir = _import(md)
    b = _ws(ir)
    assert [w["text"] for w in b["words"]] == ["CURSOR", "SUITE", "BEDBOARD"]
    # the following slide's paragraph must NOT have been swallowed into the block
    assert any(x["type"] == "paragraph" and "Plain body" in x.get("html", "") for x in ir["blocks"])


# =========================================================== render

def test_render_emits_grid_word_and_feedback_markup():
    b = _ws(_import(_MD))
    html = render.render_block(b)
    assert "data-wordsearch" in html
    assert html.count("nv-ws-cell") == b["size"] * b["size"]
    assert html.count('class="nv-ws-word"') == 3
    assert 'data-word="CURSOR"' in html and 'data-word="BEDBOARD"' in html
    assert ">Bed Board<" in html                         # display text shown, not the cleaned form
    assert "nv-ws-check" in html and "data-fb-correct" in html
    assert f"--ws-cols:{b['size']}" in html


def test_render_in_full_course():
    html = _render(_import(_MD))
    assert "data-wordsearch" in html and "nv-ws-grid" in html


# =========================================================== schema + grading

def test_schema_valid():
    validate_ir(_import(_MD), label="wordsearch")


_GRADED = """*Graded:* pass 80

## Microlearning 1: Terms

**Slide 1 — Vocabulary**

*Section:* blue · Key Terms · quiz
*WordSearch:*
term: CURSOR
term: SUITE
:::
*Section:* blue
"""


def test_graded_section_tags_the_wordsearch_objective():
    ir = _import(_GRADED)
    b = _ws(ir)
    assert b.get("objective") == "key-terms"
    assert [o["id"] for o in ir.get("objectives", [])] == ["key-terms"]
    # render surfaces the subscore hook the player reads
    assert 'data-obj="key-terms"' in render.render_block(b)


def test_inline_wordsearch_is_not_graded():
    b = _ws(_import(_MD))                                 # no graded section
    assert "objective" not in b


# =========================================================== authoring-generable

def test_block_is_taught_to_the_generator():
    # the whole point of this item: the LLM must be able to EMIT it with the course.
    guide = open(os.path.join(os.path.dirname(__file__), "..", "templates", "AUTHORING_GUIDE.md"),
                 encoding="utf-8").read()
    assert "*WordSearch:*" in guide
    assert "term:" in guide
