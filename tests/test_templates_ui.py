"""M17 — saved templates / starters, dashboard wiring (drift guard).

Guards the moving parts added for M17: the "★ Save as template" / "＋ New from
template" project-bar buttons, the per-slide "☆ Template" save button, the deck
builder's "My saved slides" insert picker, the New-from-template modal, the client
functions and their /api/template/* calls, and the server routes/handlers + init
wiring. Static-string presence only (the store logic is covered by test_template_store).
"""
import os

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
HTML = open(os.path.join(REPO, "dashboard", "index.html"), encoding="utf-8").read()
SERVER = open(os.path.join(REPO, "dashboard", "server.py"), encoding="utf-8").read()


def _fn(name):
    return HTML.split(f"function {name}(", 1)[1].split("\n}", 1)[0]


# ----- UI controls present ----------------------------------------------------

def test_project_bar_template_buttons():
    assert "saveProjectTemplate()" in HTML
    assert "openTemplatePicker()" in HTML


def test_saved_slide_picker_and_per_slide_save():
    assert 'id="deck_add_saved"' in HTML
    assert "insertSavedSlide()" in HTML
    assert "saveSlideTemplate(${i})" in HTML          # per-slide row button


def test_new_from_template_modal():
    assert 'id="tpl_modal"' in HTML
    assert 'id="tpl_list"' in HTML
    assert "closeTemplatePicker()" in HTML


# ----- client functions call the right endpoints ------------------------------

def test_save_project_template_posts():
    body = _fn("saveProjectTemplate")
    assert "/api/template/save" in body
    assert "kind:'project'" in body
    assert "project:CURRENT_PROJECT" in body


def test_save_slide_template_posts():
    body = _fn("saveSlideTemplate")
    assert "/api/template/save" in body
    assert "kind:'slide'" in body
    assert "layout:d.layout" in body and "content:d.content" in body


def test_use_template_snapshots_then_loads():
    body = _fn("useTemplate")
    assert "snapshotBefore(" in body                  # checkpoint before overwrite
    assert "/api/template/new" in body
    assert "applyProjectTemplate(" in body


def test_apply_project_template_loads_deck_and_fields():
    body = _fn("applyProjectTemplate")
    assert "DECK=m.deck.map" in body
    assert "renderDeck()" in body
    assert "sl_title" in body and "gen_title" in body


def test_delete_template_posts():
    assert "/api/template/delete" in _fn("delTemplate")


def test_init_populates_my_templates():
    assert "MY_TEMPLATES = r.my_templates" in HTML
    assert "renderSavedSlidePicker()" in HTML


# ----- server seam ------------------------------------------------------------

def test_server_routes_and_handlers():
    for route in ('"/api/template/save"', '"/api/template/new"',
                  '"/api/template/delete"', '"/api/templates"'):
        assert route in SERVER
    for fn in ("def do_save_template(p):", "def do_instantiate_template(p):",
               "def do_delete_template(p):"):
        assert fn in SERVER


def test_server_store_functions_and_init_wiring():
    for fn in ("def save_project_template(", "def save_slide_template(",
               "def instantiate_template(", "def list_templates(",
               "def place_template_script("):
        assert fn in SERVER
    assert '"my_templates": list_templates()' in SERVER
