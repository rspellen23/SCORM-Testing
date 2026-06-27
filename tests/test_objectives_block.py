"""Learning-objectives block — a first-class `objectives` type for the Slide-1
'you will be able to…' outcomes (was an ordinary bullet list).

Grammar: `*Objectives:* [intro]` + `- ` bullets. The text after the marker is an
optional lead-in (a default is rendered when omitted). Wired through all four
registry sites (covered by test_block_registry); here we check parse + render.
"""
import os
import tempfile

import blocks
import md_import
import render


def _import(md):
    f = tempfile.NamedTemporaryFile("w", suffix=".md", delete=False, encoding="utf-8")
    f.write(md); f.close()
    try:
        ir, _ = md_import.import_md(f.name, which=1)
    finally:
        os.unlink(f.name)
    return ir


_MD = ("## Microlearning 1: Demo\n\n"
       "**Slide 1 — Learning Objectives**\n"
       "*Visual:* graphic · obj · slot: `obj`\n"
       "*Objectives:* After this lesson, you will be able to:\n"
       "- Identify the three transfer types\n"
       "- Decide which queue a request belongs in\n"
       "- Escalate an urgent case correctly\n\n"
       "**Slide 2 — Body**\nSome teaching.\n")


def test_objectives_is_a_stable_authorable_block():
    assert "objectives" in blocks.authorable_types()
    assert blocks.BLOCKS["objectives"]["status"] == blocks.STABLE


def test_objectives_parses_intro_and_items():
    ir = _import(_MD)
    ob = next(b for b in ir["blocks"] if b["type"] == "objectives")
    assert ob["intro"] == "After this lesson, you will be able to:"
    assert ob["items"] == [
        "Identify the three transfer types",
        "Decide which queue a request belongs in",
        "Escalate an urgent case correctly",
    ]


def test_objectives_default_intro_when_omitted():
    block, _ = md_import._parse_objectives(["*Objectives:*", "- One", "- Two", ""], 0)
    assert "intro" not in block  # no intro stored; the renderer supplies the default
    assert block["items"] == ["One", "Two"]
    html = render.render_block(block)
    assert "After this lesson, you will be able to:" in html


def test_objectives_renders_semantic_section():
    ir = _import(_MD)
    ob = next(b for b in ir["blocks"] if b["type"] == "objectives")
    html = render.render_block(ob)
    assert 'class="nv-block nv-objectives"' in html
    assert 'aria-label="Learning objectives"' in html
    assert html.count("<li>") == 3


def test_objectives_alias_learning_objectives():
    block, _ = md_import._parse_objectives(["*Learning Objectives:* You will:", "- Do a thing"], 0)
    assert block["items"] == ["Do a thing"]
    assert block["intro"] == "You will:"
