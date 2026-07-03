"""M11 — standalone interactive HTML deck export.

`slide_svg.render_deck_html` turns an ordered deck into ONE self-contained .html
file that opens offline: each slide's poster SVG and per-slide speaker notes are
embedded, plus a tiny inline viewer (keyboard nav + presenter-notes toggle). The
DoD is self-containment — these tests assert there are no external asset loads,
that notes ride along, that a `</script>` in content can't break out of the data
island, and that the `deck --format html` CLI writes the same file to disk.
"""
import os
import re
import shutil
import subprocess
import types

import pytest

import slide_svg
import brand as brandmod
import cli


def _deck():
    return [
        {"layout": "title",
         "content": {"title": "Quarterly Review", "subtitle": "FY26 wrap"},
         "notes": "Open with the headline number, then slow down."},
        {"layout": "infographic",
         "content": {"title": "Highlights", "left": {"items": ["Up 12%", "On budget"]}},
         "notes": ""},
    ]


def _html():
    b = brandmod.load_brand("teletracking")
    return slide_svg.render_deck_html(_deck(), b, title="Quarterly Review")


# ----- self-containment (the DoD) --------------------------------------------

def test_is_a_full_standalone_document():
    html = _html()
    assert html.startswith("<!doctype html>")
    assert "</html>" in html
    assert "<title>Quarterly Review</title>" in html


def test_no_external_asset_loads():
    """Nothing is fetched from the network or the filesystem: no external script,
    stylesheet, or resource href/src, and no file:// references. (SVG namespace
    `xmlns="http://www.w3.org/2000/svg"` is a namespace literal, not a fetch.)"""
    html = _html()
    assert "<script src" not in html
    assert "<link " not in html
    assert 'href="http' not in html
    assert 'src="http' not in html
    assert "file://" not in html
    # the only http(s) occurrences are the SVG namespace declarations
    for m in re.findall(r"https?://[^\"'\s]+", html):
        assert m.startswith("http://www.w3.org/"), m


def test_slides_embedded_as_inline_svg():
    html = _html()
    assert "<svg" in html
    # images inside slides are inlined as data URIs (offline-safe), never paths
    assert 'href="file' not in html


def test_notes_are_embedded():
    html = _html()
    assert "Open with the headline number" in html
    assert '<script id="deck-data"' in html


def test_viewer_has_keyboard_nav_and_notes_toggle():
    html = _html()
    assert "addEventListener('keydown'" in html
    assert "ArrowRight" in html and "ArrowLeft" in html
    assert "toggleNotes" in html          # the presenter-notes toggle
    assert "JSON.parse(document.getElementById('deck-data')" in html


def test_script_breakout_is_neutralised():
    """A slide whose text contains `</script>` must not terminate the data island."""
    b = brandmod.load_brand("teletracking")
    deck = [{"layout": "title",
             "content": {"title": "Bad </script> news", "subtitle": "x"},
             "notes": "literally </script> in the notes"}]
    html = slide_svg.render_deck_html(deck, b, title="</script> attack")
    # exactly the two real closing tags (deck-data island + viewer script)
    assert html.count("</script>") == 2


def test_empty_deck_renders_without_crashing():
    html = slide_svg.render_deck_html([], None, title="Empty")
    assert html.startswith("<!doctype html>")
    assert '"slides": []' in html or '"slides":[]' in html


def test_inline_viewer_js_parses_with_node(tmp_path):
    if not shutil.which("node"):
        pytest.skip("node not available")
    jsf = tmp_path / "viewer.js"
    jsf.write_text(slide_svg._DECK_HTML_JS, encoding="utf-8")
    r = subprocess.run(["node", "--check", str(jsf)], capture_output=True, text=True)
    assert r.returncode == 0, r.stderr


# ----- the CLI seam ----------------------------------------------------------

def test_cli_deck_format_html_writes_standalone_file(tmp_path):
    import json
    df = tmp_path / "deck.json"
    df.write_text(json.dumps({"slides": _deck()}), encoding="utf-8")
    out = tmp_path / "review.html"
    a = types.SimpleNamespace(content=str(df), out=str(out), brand="teletracking",
                              images=None, format="html", title="Quarterly Review",
                              transition=None, animate=None)
    cli.cmd_deck(a)
    assert out.exists()
    html = out.read_text(encoding="utf-8")
    assert html.startswith("<!doctype html>")
    assert "Open with the headline number" in html
    assert "<script src" not in html


def test_cli_deck_html_title_defaults_to_filename(tmp_path):
    import json
    df = tmp_path / "deck.json"
    df.write_text(json.dumps({"slides": _deck()}), encoding="utf-8")
    out = tmp_path / "myshow.html"
    a = types.SimpleNamespace(content=str(df), out=str(out), brand="teletracking",
                              images=None, format="html", title=None,
                              transition=None, animate=None)
    cli.cmd_deck(a)
    assert "<title>myshow</title>" in out.read_text(encoding="utf-8")
