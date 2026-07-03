"""M4 — glossary/termbank guardrail, dashboard wiring (static drift guard).

The deck-generation payload must carry `brand` so the server can load that brand's
glossary and inject the approved terms into the deck prompt — the same way the
course-generation payload (genPreflight) already does. Without this, deck prompts
would only get the universal banned-filler layer, not the brand's product terms.
"""
import os

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
HTML = open(os.path.join(REPO, "dashboard", "index.html"), encoding="utf-8").read()


def _fn(name):
    return HTML.split(f"function {name}(", 1)[1].split("\n}", 1)[0]


def test_deck_generation_payload_carries_brand():
    # M8 factored the deck payload into deckPayload(); genDeck builds from it, so
    # brand still reaches /api/generate-deck (and /api/deck-plan) via the shared helper.
    assert "brand:brand()" in _fn("deckPayload")
    assert "deckPayload()" in _fn("genDeck")


def test_course_generation_payload_still_carries_brand():
    # genPreflight feeds generate-stream / script-unit / regenerate-unit / save-course
    fn = _fn("genPreflight")
    assert "brand:brand()" in fn
