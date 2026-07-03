"""Gamification #6 — confetti CELEBRATION overlay.

`*Celebrate:* on` turns on a zero-dependency canvas confetti burst that fires at the
course's win moments: passing a graded quiz, an XP tier level-up, and reaching 100%
completion. Like the points/XP overlay it is a COURSE-LEVEL directive (NOT a block
type) and PURELY COSMETIC: it never touches the graded score, the completion gate, or
the LMS record, and the player skips it under prefers-reduced-motion. The runtime
trigger-gate + burst are DOM/rAF; the pure trigger logic (`celebrateAllowed`) is pinned
in tests/test_player.js under node --test.

Byte-identical discipline: a course WITHOUT `*Celebrate:*` gains no `celebrate` IR key
and no `data-celebrate` body attribute — the emitted HTML is unchanged.
"""
import os
import tempfile

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


def _render_html(ir):
    d = tempfile.mkdtemp()
    render.render_course(ir, os.path.join(d, "c"), brand=brandlib.load_brand("_default"))
    return open(os.path.join(d, "c", "index.html"), encoding="utf-8").read()


_KC = """**Slide 1 — Knowledge Check**
*Question:* Is the sky blue?
- A) Yes
- B) No
*Correct Answer:* A
"""

_ON = "# Course\n\n*Celebrate:* on\n\n## Microlearning 1: Unit\n\n" + _KC
_OFF = "# Course\n\n## Microlearning 1: Unit\n\n" + _KC


# --- directive parsing --------------------------------------------------------

def test_celebrate_on_enables_all_three_triggers():
    ir, _ = _import(_ON)
    assert "celebrate" in ir
    assert ir["celebrate"] == {"pass": True, "level": True, "complete": True}


def test_celebrate_absent_leaves_no_key():
    ir, _ = _import(_OFF)
    assert "celebrate" not in ir


def test_celebrate_off_disables_the_overlay():
    ir, _ = _import("# Course\n\n*Celebrate:* off\n\n## Microlearning 1: Unit\n\n" + _KC)
    assert "celebrate" not in ir


def test_celebrate_per_trigger_override_parses():
    ir, _ = _import("# Course\n\n*Celebrate:* on level=off\n\n## Microlearning 1: Unit\n\n" + _KC)
    assert ir["celebrate"] == {"pass": True, "level": False, "complete": True}


def test_celebrate_multiple_overrides_parse():
    ir, _ = _import("# Course\n\n*Celebrate:* on pass=off level=off complete=on\n\n"
                    "## Microlearning 1: Unit\n\n" + _KC)
    assert ir["celebrate"] == {"pass": False, "level": False, "complete": True}


def test_confetti_alias_works():
    ir, _ = _import("# Course\n\n*Confetti:* on\n\n## Microlearning 1: Unit\n\n" + _KC)
    assert ir["celebrate"] == {"pass": True, "level": True, "complete": True}


def test_celebrate_ir_validates_against_schema():
    ir, _ = _import(_ON)
    validate_ir(ir, label="celebrate")   # raises on schema violation


# --- render emission ----------------------------------------------------------

def test_render_emits_data_celebrate_when_enabled():
    html = _render_html(_import(_ON)[0])
    assert "data-celebrate=" in html
    # the config JSON rides the body attribute
    assert "&quot;pass&quot;: true" in html or '"pass": true' in html


def test_render_per_trigger_flags_ride_the_attr():
    ir, _ = _import("# Course\n\n*Celebrate:* on level=off\n\n## Microlearning 1: Unit\n\n" + _KC)
    html = _render_html(ir)
    assert "data-celebrate=" in html
    assert ("&quot;level&quot;: false" in html) or ('"level": false' in html)


def test_render_absent_is_byte_identical():
    import re
    on = _render_html(_import(_ON)[0])
    off = _render_html(_import(_OFF)[0])
    assert "data-celebrate" not in off
    # the ONLY change the directive makes is the ` data-celebrate="..."` attribute on <body>;
    # strip it and the two documents are identical
    on_stripped = re.sub(r' data-celebrate="[^"]*"', "", on)
    assert on_stripped == off


def test_render_no_persistent_confetti_dom():
    # the burst canvas is created ad hoc by the player — it must NOT be pre-rendered into the page
    html = _render_html(_import(_ON)[0])
    assert 'class="nv-confetti"' not in html


# --- authoring-generable ------------------------------------------------------

def test_directive_is_taught_to_the_generator():
    guide = open(os.path.join(os.path.dirname(__file__), "..", "templates", "AUTHORING_GUIDE.md"),
                 encoding="utf-8").read()
    assert "*Celebrate:*" in guide
    assert "confetti" in guide.lower()
