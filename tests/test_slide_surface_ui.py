"""Slide Review surface — PowerPoint-style edit layout (Stage 1).

The stacked list of slide cards became a thumbnail RAIL on the left + the SELECTED
slide shown big on the right, with the per-slide controls (layout / theme / transition
/ regenerate / move / remove / guide / notes) docked ABOVE the canvas and the inline
text editor below it. A new SEL index tracks the selected slide; the rail thumbs and the
big canvas share the same poster SVG (it scales via its viewBox).

Static drift guards over the dashboard wiring. The editor field walker is covered by
tests/test_slide_editor_ui.py + tests/test_slide_editor.js.
"""
import os

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
HTML = open(os.path.join(REPO, "dashboard", "index.html"), encoding="utf-8").read()


def _fn(name):
    return HTML.split(f"function {name}(", 1)[1].split("\n}", 1)[0]


def test_sel_state_declared():
    assert "DECK=[], SEL=0" in HTML                       # selected-slide index lives beside DECK


def test_renderdeck_builds_rail_and_pane():
    rd = _fn("renderDeck")
    assert 'class="deck-edit"' in rd
    assert 'class="deck-rail"' in rd and 'class="deck-pane"' in rd
    assert "DECK.map((d,i)=>" in rd                       # rail iterates ALL slides
    assert 'class="rail-item' in rd and "selectSlide(${i})" in rd
    assert 'id="sl_thumb_${i}"' in rd                     # rail thumbs keep the painted-thumb id
    assert "DECK[SEL]" in rd                              # pane renders the selected slide only


def test_pane_has_controls_above_big_canvas_and_editor_below():
    rd = _fn("renderDeck")
    # order in the pane: controls bar -> big canvas -> editor panel
    pane = rd.split('class="deck-pane"', 1)[0]
    assert "slideControlsHtml(d,i,sc)" in rd              # controls docked above
    assert 'class="big-canvas" id="big_canvas"' in rd     # the big editable slide
    assert "openShowAt(${i})" in rd                       # clicking it opens the slideshow
    assert 'id="sl_edit_${i}"' in rd                      # inline editor still present below


def test_controls_moved_into_helper():
    ctl = _fn("slideControlsHtml")
    for hook in ("deckSetLayout(${i}", "deckSetTheme(${i}", "deckSetTransition(${i}",
                 "regenSlide(${i})", "deckMove(${i},-1)", "deckRemove(${i})",
                 "DECK[${i}].notes=this.value"):
        assert hook in ctl, hook


def test_selectslide_sets_sel_and_rerenders():
    ss = _fn("selectSlide")
    assert "SEL=i" in ss and "renderDeck()" in ss
    assert "i===SEL" in ss                                # no-op when already selected


def test_paint_big_canvas_shares_thumb_svg():
    pt = _fn("paintThumbs")
    assert "paintBig()" in pt
    pb = _fn("paintBig")
    assert "big_canvas" in pb and "THUMB_CACHE[key]" in pb
    ft = _fn("fetchThumb")
    assert "i===SEL" in ft and "big.innerHTML=res.svg" in ft  # fetch mirrors onto the big canvas


def test_add_move_remove_keep_sel_in_sync():
    assert "SEL=DECK.length-1" in _fn("deckAdd")          # new slide selected
    dm = _fn("deckMove")
    assert "if(SEL===i) SEL=j" in dm                      # selection follows the moved slide
    dr = _fn("deckRemove")
    assert "if(i<SEL) SEL--" in dr and "SEL>=DECK.length" in dr


def test_surface_css_present():
    for sel in (".deck-edit", ".deck-rail", ".deck-pane", ".rail-item", ".rail-item.sel",
                ".rail-thumb", ".big-canvas", ".slide-row.panectl"):
        assert sel in HTML, sel
    # the old stacked-card thumbnail rule is gone
    assert ".slide-thumb " not in HTML and ".slide-thumb{" not in HTML
