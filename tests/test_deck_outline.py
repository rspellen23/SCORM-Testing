"""M8 — editable deck outline before build.

`build_deck_plan_prompt` drafts a strict SLIDE outline (suggested layout + title +
one-liner); `parse_deck_plan` reads it back tolerantly; the approved outline feeds
`build_deck_prompt(outline=...)` which PINS the sequence/titles/layouts. With no
outline the deck prompt stays byte-identical to before.
"""
import authoring as A


# ---- outline prompt -----------------------------------------------------------

def test_plan_prompt_asks_for_slide_lines_and_rationale():
    p = A.build_deck_plan_prompt("Onboarding", "the basics", "new hires", None, "SRC")
    assert "SLIDE | <layout> | <short slide title> |" in p
    assert "RATIONALE:" in p
    assert "ONLY the slide outline" in p
    assert "SRC" in p
    # definition fields surface
    assert "PRESENTATION TITLE: Onboarding" in p
    assert "AUDIENCE: new hires" in p
    assert "the basics" in p


def test_plan_prompt_lists_layouts_and_gates_image_layouts_on_images():
    no_img = A.build_deck_plan_prompt("T", "", "", None, "SRC")
    assert "- divider:" in no_img and "- infographic:" in no_img
    assert "- image:" not in no_img and "- imagetext:" not in no_img
    with_img = A.build_deck_plan_prompt("T", "", "", None, "SRC", images=["a.png"])
    assert "- image:" in with_img and "- imagetext:" in with_img


def test_plan_prompt_fixed_count_when_n_given():
    assert "Produce exactly 7 slides." in A.build_deck_plan_prompt("T", "", "", 7, "SRC")
    assert "typically 6–12" in A.build_deck_plan_prompt("T", "", "", None, "SRC")


# ---- outline parse ------------------------------------------------------------

def test_parse_full_form_layout_title_summary():
    raw = ("RATIONALE: opens broad, then drills in.\n"
           "SLIDE | divider | Welcome | the deck's title slide\n"
           "SLIDE | process | The steps | the three-step flow\n")
    rationale, slides = A.parse_deck_plan(raw)
    assert rationale == "opens broad, then drills in."
    assert slides == [
        {"layout": "divider", "title": "Welcome", "summary": "the deck's title slide"},
        {"layout": "process", "title": "The steps", "summary": "the three-step flow"},
    ]


def test_parse_layoutless_form_falls_back_to_infographic():
    # a layout-less `SLIDE | title | one-liner` line still yields a pickable row
    _, slides = A.parse_deck_plan("SLIDE | Some point | a single idea")
    assert slides == [{"layout": "infographic", "title": "Some point", "summary": "a single idea"}]


def test_parse_unknown_layout_falls_back():
    _, slides = A.parse_deck_plan("SLIDE | banana | Title | body")
    assert slides[0]["layout"] == "infographic"
    assert slides[0]["title"] == "Title"


def test_parse_is_tolerant_of_prefixes_and_blanks():
    raw = ("\n- SLIDE | cards | A | first\n"
           "   \n"
           "# SLIDE 2 | timeline | B | second\n")
    _, slides = A.parse_deck_plan(raw)
    assert [s["layout"] for s in slides] == ["cards", "timeline"]
    assert [s["title"] for s in slides] == ["A", "B"]


def test_parse_drops_empty_slide_lines():
    _, slides = A.parse_deck_plan("SLIDE | divider |  | \nSLIDE | cards | Real | x")
    assert len(slides) == 1 and slides[0]["title"] == "Real"


# ---- outline drives generation (byte-identical when absent) -------------------

def test_deck_prompt_byte_identical_when_no_outline():
    args = ("Title", "focus", "aud", 8, "SRC")
    assert (A.build_deck_prompt(*args)
            == A.build_deck_prompt(*args, outline=None)
            == A.build_deck_prompt(*args, outline=[]))


def test_deck_prompt_injects_approved_outline():
    outline = [
        {"layout": "divider", "title": "Welcome", "summary": "the title"},
        {"layout": "process", "title": "How it works", "summary": "the flow"},
    ]
    p = A.build_deck_prompt("T", "", "", None, "SRC", outline=outline)
    assert "APPROVED SLIDE OUTLINE" in p
    assert "Produce EXACTLY these 2 slides" in p
    assert "1. [divider] Welcome — the title" in p
    assert "2. [process] How it works — the flow" in p
    # the pinned outline REPLACES the free "typically 6–12" guidance
    assert "typically 6–12" not in p


def test_generate_deck_threads_outline_into_prompt(monkeypatch):
    monkeypatch.setattr(A, "read_sources", lambda f, urls=None: ("source text", ["a.md"], []))
    seen = {}

    def fake_cli(provider, prompt, model=None):
        seen["prompt"] = prompt
        return True, '{"slides":[{"layout":"divider","content":{"title":"Welcome"}}]}', ""

    monkeypatch.setattr(A, "run_cli", fake_cli)
    out = A.generate_deck("claude", "/src",
                          outline=[{"layout": "divider", "title": "Welcome", "summary": "hi"}])
    assert out["ok"] is True
    assert "APPROVED SLIDE OUTLINE" in seen["prompt"]
    assert "[divider] Welcome — hi" in seen["prompt"]
