"""M11 — HTML deck export + slideshow presenter notes, dashboard wiring (drift guard).

Guards the moving parts in dashboard/index.html and the server seam: the Build
format selector, buildDeck carrying `format`, the slideshow presenter-notes button +
panel + toggle + 'N' key, and do_deck branching on format to write a .html file.
"""
import os

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
HTML = open(os.path.join(REPO, "dashboard", "index.html"), encoding="utf-8").read()
SERVER = open(os.path.join(REPO, "dashboard", "server.py"), encoding="utf-8").read()


def _fn(name):
    return HTML.split(f"function {name}(", 1)[1].split("\n}", 1)[0]


# ----- build format selector -------------------------------------------------

def test_format_selector_present():
    assert 'id="sl_format"' in HTML
    assert 'value="pptx"' in HTML and 'value="html"' in HTML


def test_build_payload_carries_format():
    assert "format:val('sl_format')" in _fn("buildDeck")


def test_sync_format_dims_pptx_only_controls():
    fn = _fn("syncDeckFormat")
    assert "sl_transition" in fn and "sl_animate" in fn
    assert "disabled=html" in fn


# ----- slideshow presenter notes ---------------------------------------------

def test_slideshow_notes_button_and_panel_exist():
    assert 'id="show_notes_btn"' in HTML
    assert 'id="show_notes"' in HTML
    assert "toggleShowNotes()" in HTML


def test_show_render_paints_notes():
    assert "paintShowNotes()" in _fn("showRender")


def test_n_key_toggles_notes_in_slideshow():
    fn = _fn("showKey")
    assert "toggleShowNotes()" in fn
    assert "'N'" in fn or "'n'" in fn


def test_paint_show_notes_reads_deck_notes():
    fn = _fn("paintShowNotes")
    assert "DECK[SHOW_I]" in fn
    assert "No notes for this slide" in fn


# ----- server seam -----------------------------------------------------------

def test_server_do_deck_branches_on_format():
    assert 'p.get("format") == "html"' in SERVER
    assert '"--format", "html"' in SERVER
