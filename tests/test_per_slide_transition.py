"""Per-slide transitions (slide review surface).

The deck had a single whole-deck transition. Now each slide may carry its own
"transition" (sibling to layout/theme/notes); it overrides the deck-wide default,
and "none" opts a slide out even when the deck has one. The override rides every
paginated page of a slide. Deck-wide transition still applies to slides that don't
set their own.
"""
import os
import sys
import tempfile

import brand as brandmod
import slide_layouts as SL

from pptx import Presentation
from pptx.oxml.ns import qn

_DASH = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "dashboard")
if _DASH not in sys.path:
    sys.path.insert(0, _DASH)
import server  # noqa: E402

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
HTML = open(os.path.join(REPO, "dashboard", "index.html"), encoding="utf-8").read()


def _build(slides, transition=None):
    fd, tmp = tempfile.mkstemp(suffix=".pptx")
    os.close(fd)
    SL.export_deck(slides, tmp, brand=brandmod.load_brand("teletracking"), transition=transition)
    return tmp


def _slide_tx(path):
    """Per-slide transition effect tag (or None) in document order."""
    prs = Presentation(path)
    out = []
    for s in prs.slides:
        el = s._element.find(qn("p:transition"))
        if el is None:
            out.append(None)
        else:
            kids = list(el)
            out.append(kids[0].tag.split("}")[-1] if kids else "transition")
    return out


# --------------------------------------------------------------- export behavior

def test_per_slide_overrides_deck_default():
    slides = [{"layout": "statement", "content": {"title": "A"}, "transition": "fade"},
              {"layout": "statement", "content": {"title": "B"}}]
    tx = _slide_tx(_build(slides, transition=None))
    assert tx[0] == "fade"        # slide 1's own transition
    assert tx[1] is None          # slide 2 inherits the (absent) deck default


def test_slide_none_opts_out_of_deck_default():
    slides = [{"layout": "statement", "content": {"title": "A"}, "transition": "none"},
              {"layout": "statement", "content": {"title": "B"}}]
    tx = _slide_tx(_build(slides, transition="wipe"))
    assert tx[0] is None          # explicit "none" opts out despite the deck default
    assert tx[1] == "wipe"        # slide 2 inherits the deck default


def test_no_per_slide_transition_is_byte_identical():
    # a deck with no per-slide transitions must export exactly as before.
    # Compare the zip PART CONTENTS, not the raw file bytes: python-pptx stamps every
    # zip entry with the wall-clock save time, so two saves that straddle a 2-second
    # tick differ only in that metadata — never in deck content. Raw-byte equality was
    # therefore flaky under load (the two builds occasionally landed on opposite sides
    # of a tick); part-content equality is the real determinism guarantee we want here.
    import zipfile
    slides = [{"layout": "statement", "content": {"title": "A"}}]
    za = zipfile.ZipFile(_build(slides, transition="push"))
    zb = zipfile.ZipFile(_build(slides, transition="push"))
    a = {i.filename: za.read(i.filename) for i in za.infolist()}
    b = {i.filename: zb.read(i.filename) for i in zb.infolist()}
    assert a == b


def test_cont_carries_transition_to_every_page():
    # continuation pages of a paginated slide keep the per-slide transition
    spec = {"layout": "bullets", "content": {"items": ["x"]}, "transition": "cover"}
    out = SL._cont(spec, {"items": ["a", "b"]}, "items", ["a", "b"], is_cont=True)
    assert out["transition"] == "cover"


# --------------------------------------------------------------- server normalization

def test_do_deck_normalizes_per_slide_transition(monkeypatch):
    cap = {}
    def fake_run(args):
        cap["args"] = args
        # read back the temp content JSON the server wrote
        ci = args.index("--content")
        import json as _j
        cap["slides"] = _j.load(open(args[ci + 1]))["slides"]
        oi = args.index("--out")
        open(args[oi + 1], "wb").write(b"x")     # satisfy the exists() check
        return (True, "ok")
    monkeypatch.setattr(server, "run_cli", fake_run)
    server.do_deck({"slides": [{"layout": "statement", "content": {"title": "A"}, "transition": "fade"},
                               {"layout": "statement", "content": {"title": "B"}, "transition": "bogus"}],
                    "brand": "teletracking", "out": tempfile.mkdtemp(), "name": "t"})
    slides = cap["slides"]
    assert slides[0].get("transition") == "fade"       # valid value carried
    assert "transition" not in slides[1]               # invalid value dropped


# --------------------------------------------------------------- UI drift

def test_row_has_per_slide_transition_control():
    assert "deckSetTransition(" in HTML
    # the per-slide controls now dock above the canvas via slideControlsHtml
    ctl = HTML.split("function slideControlsHtml(", 1)[1].split("\n}", 1)[0]
    assert "deckSetTransition" in ctl
    assert "Deck transition" in ctl                     # the default option label


def test_builddeck_sends_per_slide_transition():
    fn = HTML.split("async function buildDeck(", 1)[1].split("\n}", 1)[0]
    assert "transition:d.transition" in fn
