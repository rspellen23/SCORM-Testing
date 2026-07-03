"""Audit item 2.6 — the lint catches malformed interactive blocks, and the
parser hardens what it can (clamp cardGrid columns; loosen the KC option regex).

Each malformed case must fail authoring.lint() with a clear message instead of
shipping a silently broken (unscorable / unanswerable) activity.
"""
import os
import tempfile

import authoring
import md_import

_HEAD = """## Microlearning 1: Lint Test

**Slide 1 — Learning Objectives**
*Visual:* graphic · obj · slot: `obj`
- Learn the thing

**Slide 2 — Check**
"""


def _lint(extra):
    return authoring.lint(_HEAD + extra)


# --- KC option regex loosened: lowercase letters and `.` accepted ------------

def test_kc_accepts_lowercase_and_dot():
    ok, _, errs = _lint("*Question:* Which?\n- a. First\n- b. Second\n*Correct Answer:* b\n")
    assert ok, errs


# --- KC must mark exactly one in-range correct option -----------------------

def test_kc_missing_answer_fails():
    ok, _, errs = _lint("*Question:* Which?\n- A) First\n- B) Second\n")
    assert not ok and any("exactly ONE correct" in e for e in errs), errs


def test_kc_out_of_range_answer_fails():
    ok, _, errs = _lint("*Question:* Which?\n- A) First\n- B) Second\n*Correct Answer:* C\n")
    assert not ok and any("exactly ONE correct" in e for e in errs), errs


def test_kc_fewer_than_two_options_fails():
    ok, _, errs = _lint("*Question:* Which?\n- A) Only one\n*Correct Answer:* A\n")
    assert not ok and any("fewer than 2" in e for e in errs), errs


# --- categorize items must resolve to a real bucket -------------------------

def test_categorize_good_passes():
    ok, _, errs = _lint("*Categorize:*\nbucket: Fruit\nitem: Apple -> Fruit\n")
    assert ok, errs


def test_categorize_typo_bucket_fails():
    ok, _, errs = _lint("*Categorize:*\nbucket: Fruit\nitem: Apple -> Friut\n")
    assert not ok and any("doesn't map to a real bucket" in e for e in errs), errs


# --- R6: gamification / activity blocks fail lint when they ship inert -------
# The build DROPS malformed parts (a question missing its `a:`/`option:`, a
# non-interlocking word, a <2-letter term), so an all-malformed block parses to
# an EMPTY collection and would ship unanswerable. Each must fail with a clear
# message; a well-formed one must pass.

def test_dragdrop_good_passes():
    ok, _, errs = _lint("*DragDrop:*\nzone: Left\nitem: Thing -> Left\n")
    assert ok, errs


def test_dragdrop_bad_target_fails():
    ok, _, errs = _lint("*DragDrop:*\nzone: Left\nitem: Thing -> Nowhere\n")
    assert not ok and any("doesn't map to a real zone" in e for e in errs), errs


def test_dragdrop_no_items_fails():
    ok, _, errs = _lint("*DragDrop:*\nzone: Left\n")
    assert not ok and any("*DragDrop:* needs at least one `zone:`" in e for e in errs), errs


def test_wordsearch_good_passes():
    ok, _, errs = _lint("*WordSearch:*\nterm: DASHBOARD\nterm: ESCALATE\nterm: HANDOFF\n")
    assert ok, errs


def test_wordsearch_all_too_short_fails():
    # single-letter terms are stripped → no findable words
    ok, _, errs = _lint("*WordSearch:*\nterm: A\nterm: B\n")
    assert not ok and any("no findable words" in e for e in errs), errs


def test_crossword_good_passes():
    ok, _, errs = _lint("*Crossword:*\nword: DASHBOARD | where items appear\n"
                        "word: ESCALATE | raise the priority\nword: HANDOFF | pass responsibility\n")
    assert ok, errs


def test_crossword_all_too_short_fails():
    ok, _, errs = _lint("*Crossword:*\nword: A | x\nword: B | y\n")
    assert not ok and any("no solvable entries" in e for e in errs), errs


def test_gameshow_good_passes():
    ok, _, errs = _lint("*GameShow:*\nq: Where?\na: Dashboard\noption: Archive\n")
    assert ok, errs


def test_gameshow_no_answers_fails():
    # a stem with no `a:` and no `option:` → dropped by the build → 0 slices
    ok, _, errs = _lint("*GameShow:*\nq: A stem with no answer or options\n")
    assert not ok and any("*GameShow:* produced no answerable questions" in e for e in errs), errs


def test_speedstreak_good_passes():
    ok, _, errs = _lint("*SpeedStreak:*\nq: Where?\na: Dashboard\noption: Archive\n")
    assert ok, errs


def test_speedstreak_no_answers_fails():
    ok, _, errs = _lint("*SpeedStreak:*\nq: A stem with no answer or options\n")
    assert not ok and any("*SpeedStreak:* produced no answerable questions" in e for e in errs), errs


def test_quizboard_good_passes():
    ok, _, errs = _lint("*QuizBoard:*\ncategory: Queues\nq: Where?\na: Dashboard\noption: Archive\n")
    assert ok, errs


def test_quizboard_no_tiles_fails():
    # a category whose only question has no answer/options → no surviving tile
    ok, _, errs = _lint("*QuizBoard:*\ncategory: Queues\nq: A stem with no answer\n")
    assert not ok and any("*QuizBoard:* produced no answerable tiles" in e for e in errs), errs


# --- cardGrid columns clamp to the schema max (4) ---------------------------

def test_cardgrid_columns_clamped():
    md = (_HEAD + "*Cards:* columns: 9\n::: card\ntitle: A\n:::\n")
    f = tempfile.NamedTemporaryFile("w", suffix=".md", delete=False, encoding="utf-8")
    f.write(md)
    f.close()
    try:
        ir, _ = md_import.import_md(f.name, which=1)
    finally:
        os.unlink(f.name)
    grid = next(b for b in ir["blocks"] if b["type"] == "cardGrid")
    assert grid["columns"] == 4, grid.get("columns")


# --- B1: a multi-scene scenario where a later scene has no choices ----------
# (the old check passed if ANY ONE scene had responses, letting dead-ends through)

_SCEN_HEAD = ("*Scenario:* A patient-flow decision\n"
              "::: scene\n"
              "title: First\n"
              "The unit is full. What do you do?\n"
              "- Escalate to the charge nurse · preferred · feedback: right call\n"
              "- Do nothing\n")


def test_scenario_dead_end_scene_fails_lint():
    extra = _SCEN_HEAD + ("::: scene\n"
                          "title: Second\n"
                          "Now the transfer arrives — but this scene has no choices.\n")
    ok, _, errs = _lint(extra)
    assert not ok and any("dead-end" in e for e in errs), errs


def test_scenario_all_scenes_with_choices_passes():
    extra = _SCEN_HEAD + ("::: scene\n"
                          "title: Second\n"
                          "The transfer arrives.\n"
                          "- Accept it · preferred · feedback: good\n"
                          "- Refuse it\n")
    ok, _, errs = _lint(extra)
    assert ok, errs


# --- B2: an objectives block with no outcome bullets ------------------------

def test_empty_objectives_block_fails_lint():
    # *Objectives:* lead-in with NO `- ` bullets under it
    ok, _, errs = _lint("*Objectives:* By the end you will be able to:\n\nSome prose.\n")
    assert not ok and any("no outcomes" in e for e in errs), errs


def test_objectives_block_with_items_passes():
    ok, _, errs = _lint("*Objectives:* By the end you will be able to:\n"
                        "- Identify the flow bottleneck\n- Escalate correctly\n")
    assert ok, errs


# --- Q3: per-section palette-variety nudge (WARN, never block) --------------
# authoring.deck_palette_warnings is a separate, non-blocking channel: it warns
# when a deck pins the SAME accent on every color-driven slide, and stays silent
# for varied or auto-cycling decks. It must NEVER affect lint_deck's block/pass.

def _slide(layout, *accents, content=None):
    """A deck slide whose content items each carry one of `accents`."""
    if content is None:
        content = {"items": [{"title": f"t{i}", "body": "b", "accent": a}
                             for i, a in enumerate(accents)]}
    return {"layout": layout, "content": content}


def test_mono_accent_deck_warns_once():
    deck = [_slide("cards", "primary", "primary"),
            _slide("infographic", "primary"),
            _slide("timeline", "primary", "primary")]
    warns = authoring.deck_palette_warnings(deck)
    assert len(warns) == 1 and "primary" in warns[0].lower(), warns
    # the nudge must NOT block the build
    ok, _, errs = authoring.lint_deck(deck)
    assert ok, errs


def test_varied_accent_deck_is_clean():
    deck = [_slide("cards", "primary", "secondary"),
            _slide("infographic", "tertiary"),
            _slide("timeline", "dark", "primary")]
    assert authoring.deck_palette_warnings(deck) == []


def test_autocycle_deck_no_explicit_accents_is_clean():
    # no "accent" keys anywhere -> renderer auto-cycles -> varied by default
    deck = [{"layout": "cards", "content": {"items": [{"title": "a", "body": "b"}]}},
            {"layout": "timeline", "content": {"items": [{"title": "c", "body": "d"}]}}]
    assert authoring.deck_palette_warnings(deck) == []


def test_single_pinned_slide_does_not_warn():
    # only one color-driven slide pins an accent -> not the "every slide" smell
    deck = [_slide("cards", "primary", "primary"),
            {"layout": "timeline", "content": {"items": [{"title": "c", "body": "d"}]}}]
    assert authoring.deck_palette_warnings(deck) == []


def test_warning_ignores_non_color_driven_layouts():
    # a bullets/quote slide pinning "accent" is not a color-driven layout
    deck = [{"layout": "bullets", "content": {"items": [{"text": "x", "accent": "primary"}]}},
            {"layout": "quote", "content": {"accent": "primary", "text": "q"}}]
    assert authoring.deck_palette_warnings(deck) == []


# --- M10: brand-compliance nudges (WARN, never block) ----------------------
# authoring.deck_brand_warnings flags off-palette colors, unknown accent tokens,
# low-contrast accent colors, and logo/theme mismatches over slide IR tokens.
# Non-blocking — must never affect lint_deck's block/pass contract.
_BRAND = {"palette": {"green": "#1EB16A", "teal": "#00A5A7", "navy": "#003E51",
                      "yellow": "#F1C700"},
          "accentSnap": ["#1EB16A", "#00A5A7", "#003E51", "#F1C700"],
          "defaultAccent": "#1EB16A"}


def test_symbolic_accents_are_clean():
    deck = [_slide("cards", "primary", "secondary"), _slide("timeline", "dark")]
    assert authoring.deck_brand_warnings(deck, brand=_BRAND) == []


def test_brand_hex_accent_is_clean():
    # an explicit BRAND hex is sanctioned -> no warning (even the green, which is
    # below the 3:1 contrast floor: brand palette is authoritative).
    deck = [_slide("cards", "#1EB16A"), _slide("timeline", "#003E51")]
    assert authoring.deck_brand_warnings(deck, brand=_BRAND) == []


def test_off_palette_hex_is_flagged():
    deck = [_slide("cards", "#FF00FF")]
    warns = authoring.deck_brand_warnings(deck, brand=_BRAND)
    assert any("off-palette" in w and "#ff00ff" in w for w in warns), warns


def test_unknown_accent_token_is_flagged():
    deck = [_slide("cards", "magenta")]
    warns = authoring.deck_brand_warnings(deck, brand=_BRAND)
    assert any("unknown accent" in w and "magenta" in w for w in warns), warns


def test_low_contrast_off_palette_color_is_flagged():
    # a pale off-brand color: off-palette AND below the contrast floor vs white.
    deck = [_slide("cards", "#FFF3B0")]
    warns = authoring.deck_brand_warnings(deck, brand=_BRAND)
    assert any("low-contrast" in w and "#fff3b0" in w for w in warns), warns
    assert any("off-palette" in w for w in warns), warns


def test_logo_variant_theme_mismatch_is_flagged():
    deck = [{"layout": "image", "theme": "light",
             "content": {"image": "logo-white.png"}}]
    warns = authoring.deck_brand_warnings(deck, brand=_BRAND)
    assert any("light theme" in w and "logo-white.png" in w for w in warns), warns
    # the inverse: color logo on dark
    deck2 = [{"layout": "image", "theme": "dark",
              "content": {"image": "logo-color.png"}}]
    warns2 = authoring.deck_brand_warnings(deck2, brand=_BRAND)
    assert any("dark theme" in w and "logo-color.png" in w for w in warns2), warns2


def test_logo_without_explicit_theme_does_not_warn():
    # absent theme uses the brand default -> not a misuse
    deck = [{"layout": "image", "content": {"image": "logo-white.png"}}]
    assert authoring.deck_brand_warnings(deck, brand=_BRAND) == []


def test_brand_warnings_never_block_lint_deck():
    deck = [_slide("cards", "#FF00FF", "magenta")]
    assert authoring.deck_brand_warnings(deck, brand=_BRAND)  # warns
    ok, _, errs = authoring.lint_deck(deck)
    assert ok, errs  # but the build still passes


def test_contrast_ratio_helper_matches_wcag():
    # black-on-white is the max 21:1; white-on-white is the min 1:1.
    assert round(authoring._contrast_ratio("#000000", "#ffffff"), 1) == 21.0
    assert round(authoring._contrast_ratio("#ffffff", "#ffffff"), 1) == 1.0
