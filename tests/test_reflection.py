"""reflection — a free-text / open-response block (C7).

The learner types a response into a textarea and, on submit, a model answer +
rubric criteria REVEAL for self-assessment. It is NON-GRADED (completion-only):
it never carries an `objective`, is never tagged with `data-obj`, and never
reaches the graded score, the pass gate, or points/XP. There is no runtime AI
scorer — a published SCORM package runs offline — so the `model:` answer and
`criteria:` are authored at build time (the LLM writes them from the course
content), giving the learner a concrete benchmark to self-check against.

This file covers: the grammar → IR (prompt on the header, multi-line prompt,
`model:`/`criteria:` capture, both optional, the unclosed-fence boundary), the
render data-* attributes (textarea, the hidden reveal region, the empty-reveal
case, and crucially NO data-obj), that a reflection in a graded *Section:* stays
ungraded, schema validity, the dedicated no-prompt lint, the block registry, and
that the block is teachable to the generator. The player-side suspend/resume of
the typed text is pinned in tests/test_player.js.
"""
import os
import tempfile

import blocks
import md_import
import render
from authoring import lint
from ir_validate import validate_ir


def _import(md, which=1):
    f = tempfile.NamedTemporaryFile("w", suffix=".md", delete=False, encoding="utf-8")
    f.write(md)
    f.close()
    try:
        return md_import.import_md(f.name, which=which)[0]
    finally:
        os.unlink(f.name)


def _rf(ir):
    return next(b for b in ir["blocks"] if b["type"] == "reflection")


_MD = """## Microlearning 1: Escalation

**Slide 1 — Reflect**

*Reflection:* How would you apply the escalation policy to a delay you have seen?
Think about who you notify first.
model: A strong answer names the on-call coordinator first, cites the 15-minute threshold, and documents the delay.
criteria: Correct first point of contact
criteria: The time threshold
criteria: Documentation
:::
"""


# =========================================================== grammar → IR

def test_grammar_captures_prompt_model_and_criteria():
    b = _rf(_import(_MD))
    assert "escalation policy" in b["prompt"]
    assert "on-call coordinator" in b["model"]
    assert b["criteria"] == [
        "Correct first point of contact",
        "The time threshold",
        "Documentation",
    ]


def test_prompt_absorbs_prose_lines_before_the_first_key():
    # the line after the marker (before model:/criteria:) extends the prompt
    b = _rf(_import(_MD))
    assert "Think about who you notify first" in b["prompt"]


def test_model_and_criteria_are_optional():
    md = """## Microlearning 1: Reflect

**Slide 1 — Reflect**

*Reflection:* What is one thing you will do differently after this lesson?
:::
"""
    b = _rf(_import(md))
    assert "do differently" in b["prompt"]
    assert "model" not in b
    assert "criteria" not in b


def test_aliases_parse():
    for marker in ("*Reflect:*", "*OpenResponse:*", "*FreeText:*"):
        md = f"""## Microlearning 1: Reflect

**Slide 1 — Reflect**

{marker} A prompt.
:::
"""
        b = _rf(_import(md))
        assert b["type"] == "reflection"


def test_unclosed_block_stops_at_the_next_slide_marker():
    md = """## Microlearning 1: Reflect

**Slide 1 — Reflect**

*Reflection:* A prompt with no closing fence.
model: A model answer.

**Slide 2 — Next**

A following paragraph.
"""
    ir = _import(md)
    b = _rf(ir)
    assert "model answer" in b["model"]
    # the reflection must not swallow the next slide's content
    assert any("following paragraph" in (bl.get("html") or "") for bl in ir["blocks"])


# =========================================================== render

def test_render_emits_textarea_and_reveal_region():
    html = render.render_block(_rf(_import(_MD)))
    assert "data-reflection" in html
    assert 'class="nv-rf-input"' in html
    assert "nv-rf-submit" in html
    assert 'class="nv-rf-answer"' in html and "hidden" in html
    assert "on-call coordinator" in html
    assert "Correct first point of contact" in html


def test_render_is_never_graded():
    # the crux: a reflection carries NO data-obj (it can never contribute a subscore)
    html = render.render_block(_rf(_import(_MD)))
    assert "data-obj" not in html


def test_render_without_model_or_criteria_omits_the_reveal_region():
    md = """## Microlearning 1: Reflect

**Slide 1 — Reflect**

*Reflection:* A bare reflection prompt.
:::
"""
    html = render.render_block(_rf(_import(md)))
    assert "data-reflection" in html
    assert 'class="nv-rf-answer"' not in html


def test_render_in_full_course():
    import brand as brandlib
    d = tempfile.mkdtemp()
    render.render_course(_import(_MD), os.path.join(d, "c"), brand=brandlib.load_brand("_default"))
    html = open(os.path.join(d, "c", "index.html"), encoding="utf-8").read()
    assert "data-reflection" in html and "nv-rf-input" in html


# =========================================================== non-graded guarantee

_GRADED = """*Graded:* pass 80

## Microlearning 1: Review

**Slide 1 — Quiz**

*Section:* blue · Review · quiz
*Reflection:* Reflect on how you would apply this.
model: A thoughtful application to the learner's own unit.
criteria: Specific
criteria: Actionable
:::
*Section:* blue
"""


def test_reflection_in_a_graded_section_stays_ungraded():
    ir = _import(_GRADED)
    b = _rf(ir)
    # a reflection is NEVER objective-tagged, even inside a graded *Section:*
    assert "objective" not in b
    assert "data-obj" not in render.render_block(b)


# =========================================================== schema

def test_schema_valid():
    validate_ir(_import(_MD), label="reflection")
    validate_ir(_import(_GRADED), label="reflection-graded")


# =========================================================== lint

def test_lint_flags_a_reflection_with_no_prompt():
    md = """## Microlearning 1: Reflect

**Slide 1 — Reflect**

*Reflection:*
model: An orphaned model answer with no question.
:::
"""
    ok, _, errors = lint(md)
    assert not ok
    assert any("Reflection" in e and "no prompt" in e for e in errors)


def test_lint_passes_a_well_formed_reflection():
    ok, _, errors = lint(_MD)
    assert ok, errors


# =========================================================== registry + generator

def test_reflection_is_a_stable_registered_block():
    assert "reflection" in blocks.BLOCKS
    assert blocks.BLOCKS["reflection"]["status"] == blocks.STABLE
    assert "reflection" not in blocks.coming_soon_types()


def test_block_is_taught_to_the_generator():
    guide = open(os.path.join(os.path.dirname(__file__), "..", "templates", "AUTHORING_GUIDE.md"),
                 encoding="utf-8").read()
    assert "*Reflection:*" in guide
    assert "model:" in guide and "criteria:" in guide
