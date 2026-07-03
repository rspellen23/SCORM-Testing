"""Gamification #3 — points/XP MOTIVATIONAL overlay.

`*Points:* on` turns on a topbar HUD that auto-derives an XP total (every scorable block
weighted by category — check / question / game — with partial-credit blocks pro-rata) and
a level tier. It is PURELY COSMETIC: it never touches the graded score, the completion gate,
or the LMS score, and the player re-derives it from the same block state already persisted
in suspend_data (the runtime/tier math is pinned in tests/test_player.js under node --test).

Byte-identical discipline: a course WITHOUT `*Points:*` gains no `xp` IR key, no `data-xp`
body attribute, and no `.nv-xp` HUD element — the emitted HTML is unchanged.
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

_ON = "# Course\n\n*Points:* on\n\n## Microlearning 1: Unit\n\n" + _KC
_OFF = "# Course\n\n## Microlearning 1: Unit\n\n" + _KC


# --- directive parsing --------------------------------------------------------

def test_points_on_sets_xp_config_with_defaults():
    ir, _ = _import(_ON)
    assert "xp" in ir
    assert ir["xp"]["weights"] == {"check": 10, "question": 15, "game": 20}
    # default tiers span Novice(0) .. Expert(1.0)
    tiers = ir["xp"]["tiers"]
    assert tiers[0] == ["Novice", 0.0]
    assert tiers[-1] == ["Expert", 1.0]


def test_points_absent_leaves_no_xp_key():
    ir, _ = _import(_OFF)
    assert "xp" not in ir


def test_points_off_disables_the_overlay():
    ir, _ = _import("# Course\n\n*Points:* off\n\n## Microlearning 1: Unit\n\n" + _KC)
    assert "xp" not in ir


def test_points_weight_overrides_parse_on_the_same_line():
    ir, _ = _import("# Course\n\n*Points:* on check=5 question=12 game=30\n\n"
                    "## Microlearning 1: Unit\n\n" + _KC)
    assert ir["xp"]["weights"] == {"check": 5, "question": 12, "game": 30}


def test_points_partial_override_keeps_other_defaults():
    ir, _ = _import("# Course\n\n*Points:* on game=25\n\n## Microlearning 1: Unit\n\n" + _KC)
    assert ir["xp"]["weights"] == {"check": 10, "question": 15, "game": 25}


def test_xp_ir_validates_against_schema():
    ir, _ = _import(_ON)
    validate_ir(ir, label="xp")   # raises on schema violation


# --- render emission ----------------------------------------------------------

def test_render_emits_data_xp_and_hud_when_enabled():
    ir, _ = _import(_ON)
    html = _render_html(ir)
    assert "data-xp=" in html
    assert 'class="nv-xp"' in html
    assert 'class="nv-xp-pts"' in html
    assert 'class="nv-xp-tier"' in html
    # the HUD ships hidden — the player reveals it once it confirms scorable blocks exist
    assert "nv-xp" in html and "hidden" in html


def test_render_omits_xp_entirely_when_disabled():
    ir, _ = _import(_OFF)
    html = _render_html(ir)
    assert "data-xp=" not in html
    assert "nv-xp" not in html


def test_data_xp_payload_carries_weights_and_tiers():
    import json
    ir, _ = _import("# Course\n\n*Points:* on check=7\n\n## Microlearning 1: Unit\n\n" + _KC)
    html = _render_html(ir)
    # pull the data-xp attribute value back out and parse it
    marker = 'data-xp="'
    start = html.index(marker) + len(marker)
    end = html.index('"', start)
    raw = html[start:end].replace("&quot;", '"').replace("&#34;", '"')
    cfg = json.loads(raw)
    assert cfg["w"]["check"] == 7
    assert cfg["t"][0] == ["Novice", 0.0]


def test_xp_overlay_does_not_touch_grading_keys():
    # A purely cosmetic overlay: turning it on must not make an ungraded course graded,
    # nor alter the gate/objectives keys.
    ir, _ = _import(_ON)
    assert ir["graded"] is False
    assert ir["objectives"] == []
