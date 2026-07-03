"""View-script modal (course stage 2).

After scripts are generated, the per-module list offered Regenerate immediately —
but at that point the drafted script can't be SEEN yet, so a blind re-roll has no
basis. This adds a read-only View modal (full script + per-module jump) beside the
Regenerate buttons. The script (md/IR) stays the canonical edit surface, so the
viewer is deliberately read-only. Static drift guards over the dashboard wiring.
"""
import os
import re

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
HTML = open(os.path.join(REPO, "dashboard", "index.html"), encoding="utf-8").read()


def _fn(name):
    return HTML.split(f"function {name}(", 1)[1].split("\n}", 1)[0]


def test_modal_markup_present_and_readonly():
    assert 'id="scriptview"' in HTML
    assert 'id="sv_body"' in HTML
    # the viewer is a <pre>, not an editable surface
    assert re.search(r'<pre id="sv_body"', HTML)
    assert "<textarea id=\"sv_body\"" not in HTML


def test_module_list_offers_view_alongside_regenerate():
    fn = _fn("loadModules")
    assert "viewScript()" in fn                    # full-script button
    assert "viewScript(${m.which})" in fn          # per-module jump
    assert "regenModule(${m.which})" in fn         # regenerate is KEPT


def test_view_script_fetches_readtext_and_jumps_to_module():
    fn = _fn("viewScript")
    assert "/api/readtext?path=" in fn
    assert "CURRENT_SCRIPT" in fn
    assert "Microlearning" in fn                   # builds the heading regex to scroll to
    assert "scriptview" in fn                       # shows the modal


def test_modal_closes_on_escape_and_backdrop():
    assert "closeScriptView" in HTML
    assert "Escape" in HTML and "scriptview" in HTML
