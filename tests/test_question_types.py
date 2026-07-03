"""M12 — more question types: matching · sequencing · fill-in-the-blank.

Each mirrors the `categorize` interactive block (author → render → self-score →
resume) but scores with PARTIAL credit. The pure scorers + suspend/resume are
pinned in tests/test_player.js (node --test); this file covers the grammar → IR,
render data-* attributes, lint, and schema validity.
"""
import os
import tempfile

import authoring
import md_import
import render
import brand as brandlib
from ir_validate import validate_ir


def _import(md, which=1):
    f = tempfile.NamedTemporaryFile("w", suffix=".md", delete=False, encoding="utf-8")
    f.write(md)
    f.close()
    try:
        return md_import.import_md(f.name, which=which)
    finally:
        os.unlink(f.name)


def _render(ir):
    d = tempfile.mkdtemp()
    render.render_course(ir, os.path.join(d, "c"), brand=brandlib.load_brand("_default"))
    return open(os.path.join(d, "c", "index.html"), encoding="utf-8").read()


def _block(ir, t):
    return next(b for b in ir["blocks"] if b["type"] == t)


# =========================================================== matching

_MATCH = """# C

## Microlearning 1: U

**Slide 1 — Match**
*Matching:* prompt: Match each term to its meaning.
pair: Alpha -> First letter
pair: Beta -> Second letter
pair: Gamma -> Third letter
:::
"""


def test_matching_parses_pairs():
    b = _block(_import(_MATCH)[0], "matching")
    assert b["prompt"] == "Match each term to its meaning."
    assert [(p["id"], p["left"], p["right"]) for p in b["pairs"]] == [
        ("p1", "Alpha", "First letter"),
        ("p2", "Beta", "Second letter"),
        ("p3", "Gamma", "Third letter"),
    ]


def test_matching_accepts_arrow_variants():
    md = _MATCH.replace("Alpha -> First letter", "Alpha => First letter")
    b = _block(_import(md)[0], "matching")
    assert b["pairs"][0]["right"] == "First letter"


def test_matching_ir_validates():
    validate_ir(_import(_MATCH)[0], label="match")


def test_matching_render_emits_data_attrs():
    html = _render(_import(_MATCH)[0])
    assert "data-match" in html
    assert html.count("data-answer=") == 3
    assert "nv-match-check" in html and "nv-match-pick" in html


def test_matching_render_reverses_option_order():
    # options list every right in REVERSED authored order so it doesn't mirror the rows
    html = _render(_import(_MATCH)[0])
    import re
    first_select = html.split('nv-match-pick', 1)[1].split("</select>", 1)[0]
    ids = re.findall(r'<option value="(p\d)">', first_select)
    assert ids == ["p3", "p2", "p1"]


def test_matching_lint_good_passes():
    ok, _, errs = authoring.lint(_MATCH)
    assert ok, errs


def test_matching_lint_single_pair_fails():
    md = """# C

## Microlearning 1: U

**Slide 1 — Match**
*Matching:*
pair: Only -> One
:::
"""
    ok, _, errs = authoring.lint(md)
    assert not ok and any("at least two" in e for e in errs), errs


def test_matching_lint_malformed_pair_drops_below_two():
    # `pair: X -> ` (empty right) fails the `-> <right>` grammar, so it's dropped; with only
    # one valid pair left, the "at least two" lint fires — a malformed pair can't sneak through.
    md = """# C

## Microlearning 1: U

**Slide 1 — Match**
*Matching:*
pair: Alpha -> First
pair: Beta ->
:::
"""
    ok, _, errs = authoring.lint(md)
    assert not ok and any("at least two" in e for e in errs), errs


# =========================================================== sequencing

_SEQ = """# C

## Microlearning 1: U

**Slide 1 — Order**
*Sequence:* prompt: Put the deployment steps in order.
step: Write the code
step: Review the code
step: Merge the code
step: Deploy the code
:::
"""


def test_sequence_parses_steps_in_order():
    b = _block(_import(_SEQ)[0], "sequence")
    assert b["prompt"] == "Put the deployment steps in order."
    assert [(s["id"], s["html"]) for s in b["steps"]] == [
        ("s1", "Write the code"), ("s2", "Review the code"),
        ("s3", "Merge the code"), ("s4", "Deploy the code"),
    ]


def test_sequence_order_alias():
    b = _block(_import(_SEQ.replace("*Sequence:*", "*Order:*"))[0], "sequence")
    assert len(b["steps"]) == 4


def test_sequence_ir_validates():
    validate_ir(_import(_SEQ)[0], label="seq")


def test_sequence_render_reverses_display_with_correct_positions():
    # steps are shown REVERSED (not the answer order); each carries its correct data-pos
    html = _render(_import(_SEQ)[0])
    assert "data-seq" in html and "nv-seq-check" in html
    import re
    items = re.findall(r'<li class="nv-seq-item" data-pos="(\d)"><span class="nv-seq-label">([^<]+)</span>', html)
    # first shown = last step (Deploy, pos 4); last shown = first step (Write, pos 1)
    assert items[0] == ("4", "Deploy the code")
    assert items[-1] == ("1", "Write the code")


def test_sequence_render_position_select_has_all_positions():
    html = _render(_import(_SEQ)[0])
    first_select = html.split("nv-seq-pick", 1)[1].split("</select>", 1)[0]
    import re
    assert re.findall(r'<option value="(\d)">', first_select) == ["1", "2", "3", "4"]


def test_sequence_lint_good_passes():
    ok, _, errs = authoring.lint(_SEQ)
    assert ok, errs


def test_sequence_lint_single_step_fails():
    md = """# C

## Microlearning 1: U

**Slide 1 — Order**
*Sequence:*
step: Only one
:::
"""
    ok, _, errs = authoring.lint(md)
    assert not ok and any("at least two" in e for e in errs), errs


# =========================================================== fill-in-the-blank

_FILL = """# C

## Microlearning 1: U

**Slide 1 — Fill**
*FillBlank:* prompt: Complete each sentence.
blank: The capital of France is ___. -> Paris | paris
blank: Water freezes at ___ degrees Celsius. -> 0 | zero
:::
"""


def test_fillblank_parses_before_after_and_answers():
    b = _block(_import(_FILL)[0], "fillBlank")
    assert b["prompt"] == "Complete each sentence."
    b0 = b["blanks"][0]
    assert b0["id"] == "f1" and b0["before"] == "The capital of France is" and b0["after"] == "."
    assert b0["answers"] == ["Paris", "paris"]
    assert b["blanks"][1]["answers"] == ["0", "zero"]


def test_fillblank_no_marker_puts_input_at_end():
    md = _FILL.replace("The capital of France is ___.", "Name the capital of France")
    b0 = _block(_import(md)[0], "fillBlank")["blanks"][0]
    assert b0["before"] == "Name the capital of France" and b0["after"] == ""


def test_fillblank_alias_fill():
    b = _block(_import(_FILL.replace("*FillBlank:*", "*Fill:*"))[0], "fillBlank")
    assert len(b["blanks"]) == 2


def test_fillblank_ir_validates():
    validate_ir(_import(_FILL)[0], label="fill")


def test_fillblank_render_emits_inputs_and_answers():
    html = _render(_import(_FILL)[0])
    assert "data-fill" in html and "nv-fill-check" in html
    assert html.count("nv-fill-input") == 2
    # accept-list rides in data-answers as JSON (HTML-escaped)
    assert "data-answers=" in html
    import json
    import re
    first = re.search(r'data-answers="([^"]*)"', html).group(1).replace("&quot;", '"')
    assert json.loads(first) == ["Paris", "paris"]


def test_fillblank_lint_good_passes():
    ok, _, errs = authoring.lint(_FILL)
    assert ok, errs


def test_fillblank_lint_missing_answer_fails():
    # `blank: X -> ` (no answer) fails the grammar and is dropped; with no valid blanks the
    # "no blank lines" lint fires.
    md = """# C

## Microlearning 1: U

**Slide 1 — Fill**
*FillBlank:*
blank: The answer is ___ ->
:::
"""
    ok, _, errs = authoring.lint(md)
    assert not ok and any("fill-in-the-blank" in e for e in errs), errs


# =========================================================== dragDrop

_DRAG = """# C

## Microlearning 1: U

**Slide 1 — Place**
*DragDrop:* prompt: Drag each control to its panel.
zone: Header
zone: Footer
item: Logo -> Header
item: Copyright -> Footer
:::
"""

_DRAG_DIAGRAM = """# C

## Microlearning 1: U

**Slide 1 — Label**
*DragDrop:*
image: assets/ui.png
zone: Search box @ 20,15
zone: Save button @ 80,90
item: Find a patient -> Search box
item: Commit the change -> Save button
:::
"""


def test_dragdrop_parses_zones_and_pool():
    b = _block(_import(_DRAG)[0], "dragDrop")
    assert b["prompt"] == "Drag each control to its panel."
    assert [(z["id"], z["title"]) for z in b["zones"]] == [("z1", "Header"), ("z2", "Footer")]
    # each pool item links to its correct zone id via `target`
    assert [(p["html"], p["target"]) for p in b["pool"]] == [
        ("Logo", "z1"), ("Copyright", "z2")]
    assert "src" not in b  # no diagram in the plain form


def test_dragdrop_accepts_arrow_variants():
    md = _DRAG.replace("Logo -> Header", "Logo => Header")
    b = _block(_import(md)[0], "dragDrop")
    assert b["pool"][0]["target"] == "z1"


def test_dragdrop_diagram_positions_zones():
    b = _block(_import(_DRAG_DIAGRAM)[0], "dragDrop")
    assert b["src"] == "assets/ui.png"
    assert b["zones"][0]["title"] == "Search box"
    assert (b["zones"][0]["x"], b["zones"][0]["y"]) == (20.0, 15.0)
    assert (b["zones"][1]["x"], b["zones"][1]["y"]) == (80.0, 90.0)
    # the @ x,y coordinate must not bleed into the linkable zone name
    assert b["pool"][0]["target"] == "z1"


def test_dragdrop_ir_validates():
    validate_ir(_import(_DRAG)[0], label="drag")
    validate_ir(_import(_DRAG_DIAGRAM)[0], label="drag-diagram")


def test_dragdrop_render_emits_data_attrs():
    html = _render(_import(_DRAG)[0])
    assert "data-drag" in html
    assert html.count('data-target=') == 2      # one per draggable label
    assert html.count('data-zone=') == 2         # one per drop zone
    assert 'draggable="true"' in html
    assert "nv-drag-check" in html and "nv-drag-pick" in html


def test_dragdrop_render_places_zones_over_diagram():
    html = _render(_import(_DRAG_DIAGRAM)[0])
    assert "nv-drag-diagram" in html and 'src="assets/ui.png"' in html
    # positioned zone carries a left/top percent style
    assert "left:20" in html and "top:15" in html


def test_dragdrop_pick_lists_every_zone():
    # the accessible "Place in…" select must offer every zone as an option
    html = _render(_import(_DRAG)[0])
    first_select = html.split('nv-drag-pick', 1)[1].split("</select>", 1)[0]
    import re
    ids = re.findall(r'<option value="(z\d)">', first_select)
    assert ids == ["z1", "z2"]


def test_dragdrop_lint_does_not_crash():
    # dragDrop has no dedicated lint yet; the generic lint must not choke on it.
    ok, _, errs = authoring.lint(_DRAG)
    assert isinstance(errs, list)
