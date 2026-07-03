"""P4 "describe the slide" — dashboard wiring for the deterministic layout matcher
(open follow-up #10). The engine shipped match_layout_from_intent + a match-layout
CLI in `74eb495`, but the slide editor never surfaced it. This guards the three
seams that make the "Suggest layout" control work, and re-checks the pure matcher
behind it:

  1. HTML  — the deck editor has a describe-the-slide input + Suggest button wired
             to suggestLayout(), which POSTs /api/match-layout and drives the
             Add-slide layout picker.
  2. Server— do_POST routes /api/match-layout to do_match_layout, which allows
             image layouts (the deck picker offers them) and enriches with purpose.
  3. Core  — the matcher still resolves confident intents and flags vague ones.
"""
import os
import sys

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
HTML = open(os.path.join(REPO, "dashboard", "index.html"), encoding="utf-8").read()
SERVER = open(os.path.join(REPO, "dashboard", "server.py"), encoding="utf-8").read()
sys.path.insert(0, os.path.join(REPO, "dashboard"))
sys.path.insert(0, os.path.join(REPO, "src"))


# ----- HTML control ----------------------------------------------------------

def test_describe_the_slide_control_present():
    assert 'id="deck_intent"' in HTML                 # the sentence input
    assert "suggestLayout()" in HTML                  # button + Enter both call it


def test_suggest_layout_drives_the_add_slide_picker():
    fn = HTML.split("async function suggestLayout(", 1)[1].split("\n}", 1)[0]
    assert "/api/match-layout" in fn                  # hits the matcher endpoint
    assert "deck_add_layout" in fn                    # sets the Add-slide layout picker
    assert "recommended" in fn and "confident" in fn  # surfaces confidence


# ----- server seam -----------------------------------------------------------

def test_endpoint_is_routed():
    assert '"/api/match-layout"' in SERVER
    assert "do_match_layout(p)" in SERVER


def test_handler_allows_image_layouts_and_enriches_purpose():
    # the deck Add-slide picker includes image/imagetext, so the matcher must too
    body = SERVER.split("def do_match_layout(", 1)[1].split("\ndef ", 1)[0]
    assert "allow_image_layouts=True" in body
    assert "LAYOUT_PURPOSE" in body


# ----- pure matcher behind it ------------------------------------------------

def test_handler_resolves_confident_and_vague_intents():
    import server
    hit = server.do_match_layout({"intent": "compare the three deployment models"})
    assert hit["ok"] and hit["recommended"] == "comparison" and hit["confident"]
    assert hit["purpose"]                                   # enriched for the UI

    vague = server.do_match_layout({"intent": "umm some stuff about things"})
    assert vague["recommended"] == "bullets" and vague["confident"] is False

    empty = server.do_match_layout({"intent": "   "})
    assert empty["ok"] is False and "error" in empty


def test_handler_allows_image_intent():
    import server
    r = server.do_match_layout({"intent": "a full-bleed hero photo of the datacenter"})
    assert r["ok"] and r["recommended"] in ("image", "imagetext")
