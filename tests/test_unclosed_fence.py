"""Audit item 2.5 — an unclosed fence must not swallow the rest of the unit.

Every fenced/keyed parser (cards, accordion/process via _read_fences, categorize,
comparison, chart) stops at the next slide / unit / meta marker if the author
forgets the closing lone `:::`, instead of consuming to EOF.
"""
import os
import tempfile

import md_import


def _import(md):
    f = tempfile.NamedTemporaryFile("w", suffix=".md", delete=False, encoding="utf-8")
    f.write(md)
    f.close()
    try:
        ir, _ = md_import.import_md(f.name, which=1)
    finally:
        os.unlink(f.name)
    return ir


_HEAD = """## Microlearning 1: Fence Test

**Slide 1 — Learning Objectives**
*Visual:* graphic · objectives · slot: `obj`
- Understand fencing
"""

_TAIL = """
**Slide 9 — After**
This paragraph must survive as its own slide content.
*Statement:* I survived the unclosed fence.
"""


def _survives(block_md):
    ir = _import(_HEAD + "\n" + block_md + _TAIL)
    htext = " ".join(b.get("html", "") for b in ir["blocks"] if b["type"] == "heading")
    assert "After" in htext, f"trailing slide heading swallowed: {htext!r}"
    assert any(b["type"] == "statement" for b in ir["blocks"]), "trailing statement swallowed"
    return ir


def test_unclosed_cards_stops_at_next_slide():
    _survives("**Slide 2 — Cards**\n*Cards:*\n::: card\ntitle: A\nteaser: t\n")


def test_unclosed_accordion_stops_at_next_slide():
    _survives("**Slide 2 — Accordion**\n*Accordion:*\n::: item\ntitle: A\nbody: b\n")


def test_unclosed_categorize_stops_at_next_slide():
    _survives("**Slide 2 — Sort**\n*Categorize:*\nbucket: One\nitem: x -> One\n")


def test_unclosed_comparison_stops_at_next_slide():
    _survives("**Slide 2 — Compare**\n*Comparison:*\n::: panel\nheading: Old\n- a\n")


def test_unclosed_chart_stops_at_next_slide():
    _survives("**Slide 2 — Chart**\n*Chart:* bar\ncategories: Q1, Q2\nseries: A = 1, 2\n")
