"""Direct slide editor (slide Review surface) — inline structured fields.

The only per-slide editing used to be AI regenerate-by-prompt; now each slide has
an ✎ Edit panel of structured text fields over its content JSON. Edits write back
to DECK[i].content and repaint the live thumbnail (the Layout/Theme/Color/Transition
controls still own the style keys, so those are hidden in the editor). List items
keep their ["lead"," rest"] bold-lead pair where the schema uses it. Also fixes the
Source-&-generate copy that pointed "below" at slides that live on the next step.

Static drift guards over the wiring. The path/type CORE is exercised behaviorally in
tests/test_slide_editor.js.
"""
import os

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
HTML = open(os.path.join(REPO, "dashboard", "index.html"), encoding="utf-8").read()


def _fn(name):
    return HTML.split(f"function {name}(", 1)[1].split("\n}", 1)[0]


def test_edit_toggle_button_and_panel_present():
    ctl = _fn("slideControlsHtml")                   # controls now dock above the canvas
    assert "toggleEdit(${i})" in ctl                 # the Edit toggle
    assert 'id="sl_rowtitle_${i}"' in ctl            # title chip updates in place on edit
    rd = _fn("renderDeck")
    assert 'id="sl_edit_${i}"' in rd                 # the editor panel container (below canvas)
    assert "d._editing?slideEditorHtml(i):''" in rd  # panel renders only when editing


def test_editor_hides_style_keys():
    # the dedicated controls own these — they must not appear as text fields
    skip = HTML.split("const EDIT_SKIP=new Set(", 1)[1].split(")", 1)[0]
    for k in ("accent", "bg", "side", "theme", "columns"):
        assert f"'{k}'" in skip, k
    assert "EDIT_SKIP.has(k)" in _fn("editFields")   # and the walker honors the skip set


def test_walker_routes_text_lists_and_objects():
    ef = _fn("editFields")
    assert "isItemsArray(v)" in ef                   # string/pair lists -> item editor
    assert "isObjArray(v)" in ef                     # object lists -> card editor
    assert "editStr(${i}" in ef                      # text leaf -> live field
    assert "objAdd(${i}" in ef and "objDel(${i}" in ef


def test_items_support_bold_lead_pair():
    ih = _fn("itemsHtml")
    assert "itemBold(${i}" in ih                     # the B toggle
    assert "'lead'" in ih and "'rest'" in ih and "'plain'" in ih
    # the toggle converts string <-> ["lead",""] pair
    ib = _fn("itemBold")
    assert "Array.isArray(e)?e.join(''):[String(e||''),'']" in ib


def test_edit_commits_live_without_row_rerender():
    # text edits go through editStr -> _editCommit (model + thumb), NOT a full renderDeck
    es = _fn("editStr")
    assert "_setAt(o,path,v)" in es and "_editCommit(i,o)" in es
    ec = _fn("_editCommit")
    assert "DECK[i].content=JSON.stringify" in ec
    assert "paintThumbs()" in ec                     # live thumbnail
    assert "renderDeck" not in ec                    # caret-preserving: no row rebuild


def test_generate_copy_points_to_next_step_not_below():
    dr = _fn("deckResult")
    assert "Continue to" in dr
    assert "review &amp; edit them below" not in HTML   # the misleading copy is gone
