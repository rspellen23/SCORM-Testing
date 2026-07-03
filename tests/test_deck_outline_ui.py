"""M8 — editable deck outline, dashboard wiring (drift guard).

Guards the moving parts in dashboard/index.html and the server seam: the "Plan
outline first" button + outline container, the deckPlan/outline-editor functions,
genDeck accepting + forwarding an approved outline, and do_deck_plan + its route.
"""
import os

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
HTML = open(os.path.join(REPO, "dashboard", "index.html"), encoding="utf-8").read()
SERVER = open(os.path.join(REPO, "dashboard", "server.py"), encoding="utf-8").read()


def _fn(name):
    return HTML.split(f"function {name}(", 1)[1].split("\n}", 1)[0]


# ----- the opt-in plan button + outline container ------------------------------

def test_plan_button_and_container_present():
    assert 'id="sl_plan"' in HTML and 'onclick="deckPlan()"' in HTML
    assert 'id="deck_outline"' in HTML
    # the one-shot generate button is untouched (optional-outline design)
    assert 'id="sl_gen"' in HTML and 'onclick="genDeck()"' in HTML


# ----- deckPlan calls the new endpoint with the shared payload -----------------

def test_deckPlan_posts_to_deck_plan_endpoint():
    fn = _fn("deckPlan")
    assert "/api/deck-plan" in fn
    assert "deckPayload()" in fn
    assert "renderOutline()" in fn


def test_shared_payload_helper_exists():
    fn = _fn("deckPayload")
    for k in ("source", "nslides", "preset", "brand"):
        assert k in fn


# ----- outline editor: reorder / edit / approve --------------------------------

def test_outline_editor_functions_present():
    for name in ("renderOutline", "moveOutline", "delOutline", "addOutline",
                 "approveOutline", "syncOutline"):
        assert f"function {name}(" in HTML or f"function {name} (" in HTML


def test_outline_rows_use_layout_picker():
    fn = _fn("renderOutline")
    assert "layoutOptionsHtml(" in fn          # per-slide layout dropdown
    assert "ol-title" in fn and "ol-sum" in fn  # title + one-liner inputs


def test_approve_generates_from_outline():
    fn = _fn("approveOutline")
    assert "genDeck(" in fn                     # approved outline -> generation


# ----- genDeck accepts + forwards the approved outline -------------------------

def test_genDeck_forwards_outline():
    fn = _fn("genDeck")
    assert "outline" in fn
    assert "payload.outline" in fn


# ----- server seam -------------------------------------------------------------

def test_server_has_deck_plan_handler_and_route():
    assert "def do_deck_plan(" in SERVER
    assert "build_deck_plan_prompt(" in SERVER
    assert "parse_deck_plan(" in SERVER
    assert '"/api/deck-plan"' in SERVER


def test_generate_deck_paths_forward_outline():
    # both the one-shot and streaming deck-gen paths pass the approved outline through
    assert 'outline=p.get("outline")' in SERVER
    assert SERVER.count('outline=p.get("outline")') >= 2
