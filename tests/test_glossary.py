"""M4 — Glossary / termbank + banned-words guardrail.

The brand-level `glossary.json` (preferred terms + banned words) does two jobs:
  1. injects approved terminology into the generation prompt, and
  2. raises a BLOCKING lint error when a banned word or a wrong-term phrase
     appears in generated markdown.
Both default OFF (glossary=None / empty) so existing callers stay unchanged.
"""
import sys, os, json

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))
import authoring as A


# ----------------------------------------------------------------- loader
def test_default_glossary_has_universal_banned_list():
    g = A.load_glossary("_default")
    assert "leverage" in g["banned"] and "seamless" in g["banned"]
    assert g["preferred"] == []          # universal layer carries no product terms


def test_teletracking_glossary_merges_over_default():
    g = A.load_glossary("teletracking")
    # inherits the universal banned words...
    assert "leverage" in g["banned"]
    # ...and adds its own product preferred terms
    terms = [e["term"] for e in g["preferred"]]
    assert "Transfer IQ Pro" in terms


def test_load_glossary_unknown_brand_never_raises():
    g = A.load_glossary("no-such-brand")          # falls back to _default
    assert isinstance(g, dict) and "banned" in g and "preferred" in g


# ----------------------------------------------------------------- prompt block
def test_prompt_block_empty_when_no_glossary():
    assert A.glossary_prompt_block(None) == ""
    assert A.glossary_prompt_block({"preferred": [], "banned": []}) == ""


def test_prompt_block_lists_terms_and_banned_words():
    g = {"preferred": [{"term": "Transfer IQ Pro", "instead_of": ["the transfer tool"]}],
         "banned": ["leverage"]}
    block = A.glossary_prompt_block(g)
    assert "Transfer IQ Pro" in block
    assert "the transfer tool" in block          # the shorthand to avoid is shown
    assert "leverage" in block
    assert block.startswith("- TERMINOLOGY")      # one always-on rule line


# ----------------------------------------------------------------- lint findings
def test_lint_issues_flags_banned_word():
    g = {"preferred": [], "banned": ["leverage"]}
    issues = A.glossary_lint_issues("We will leverage the data.", g)
    assert len(issues) == 1 and "leverage" in issues[0]


def test_lint_issues_flags_wrong_term_with_approved_replacement():
    g = {"preferred": [{"term": "Transfer IQ Pro", "instead_of": ["the transfer tool"]}],
         "banned": []}
    issues = A.glossary_lint_issues("Open the transfer tool now.", g)
    assert len(issues) == 1
    assert "the transfer tool" in issues[0] and "Transfer IQ Pro" in issues[0]


def test_lint_issues_clean_text_passes():
    g = A.load_glossary("teletracking")
    assert A.glossary_lint_issues("Open Transfer IQ Pro and review the bed request.", g) == []


def test_lint_issues_ignores_code_spans_and_urls():
    g = {"preferred": [], "banned": ["leverage"]}
    assert A.glossary_lint_issues("Run `leverage --x` to start.", g) == []
    assert A.glossary_lint_issues("See https://x.test/leverage for docs.", g) == []


def test_lint_issues_whole_word_only():
    g = {"preferred": [], "banned": ["unlock"]}
    # substring inside another word must NOT fire
    assert A.glossary_lint_issues("The unlockable bonus.", g) == []
    assert A.glossary_lint_issues("Unlock the record.", g)        # standalone DOES fire


def test_lint_issues_empty_glossary_is_noop():
    assert A.glossary_lint_issues("leverage everything", None) == []
    assert A.glossary_lint_issues("leverage everything", {"preferred": [], "banned": []}) == []


# ----------------------------------------------------------------- lint() integration (blocking)
_UNIT_OK = (
    "## Microlearning 1: Submitting a Bed Request\n\n"
    "**Slide 1 — Overview**\n"
    "Open the request form and complete the fields to submit a bed request.\n\n"
    "**Slide 2 — Why it matters**\n"
    "A complete request routes the patient to the right unit without delay.\n"
)


def test_lint_blocks_banned_word_in_output():
    g = {"preferred": [], "banned": ["leverage"]}
    bad = _UNIT_OK.replace("Open the request form", "Leverage the request form")
    ok, _n, errs = A.lint(bad, glossary=g)
    assert not ok
    assert any("leverage" in e for e in errs)


def test_lint_without_glossary_is_byte_identical_behaviour():
    # the clean unit lints OK; passing no glossary adds no new findings
    ok_a, n_a, errs_a = A.lint(_UNIT_OK)
    ok_b, n_b, errs_b = A.lint(_UNIT_OK, glossary=None)
    assert (ok_a, n_a, errs_a) == (ok_b, n_b, errs_b)


def test_lint_banned_word_only_fires_with_glossary():
    bad = _UNIT_OK.replace("Open the request form", "Leverage the request form")
    ok_no_g, _n, errs_no = A.lint(bad)                 # no glossary -> term check off
    ok_g, _n2, errs_g = A.lint(bad, glossary={"preferred": [], "banned": ["leverage"]})
    assert ok_no_g and not ok_g                        # only the glossary path blocks
    assert not any("leverage" in e for e in errs_no)
    assert any("leverage" in e for e in errs_g)


# ----------------------------------------------------------------- prompt injection
def test_build_unit_prompt_injects_terminology_when_glossary_given():
    g = {"preferred": [{"term": "Transfer IQ Pro", "instead_of": ["the transfer tool"]}],
         "banned": ["leverage"]}
    unit = {"title": "X", "objective": "identify X"}
    p = A.build_unit_prompt(unit, [unit], 1, 1, "obj", "aud", "concept-explainer", "SRC",
                            glossary=g)
    assert "Transfer IQ Pro" in p and "TERMINOLOGY" in p
    p0 = A.build_unit_prompt(unit, [unit], 1, 1, "obj", "aud", "concept-explainer", "SRC")
    assert "TERMINOLOGY" not in p0                      # absent without a glossary


def test_build_prompt_and_deck_prompt_inject_terminology():
    g = {"preferred": [{"term": "Data IQ", "instead_of": []}], "banned": []}
    cp = A.build_prompt("obj", "aud", "concept-explainer", 2, "SRC", glossary=g)
    dp = A.build_deck_prompt("T", "", "", None, "SRC", glossary=g)
    assert "Data IQ" in cp and "TERMINOLOGY" in cp
    assert "Data IQ" in dp and "TERMINOLOGY" in dp
    # no glossary -> no injection
    assert "TERMINOLOGY" not in A.build_prompt("obj", "aud", "concept-explainer", 2, "SRC")
    assert "TERMINOLOGY" not in A.build_deck_prompt("T", "", "", None, "SRC")


# ----------------------------------------------------------------- shipped files parse
def test_shipped_glossary_files_are_valid_json():
    root = os.path.join(os.path.dirname(__file__), "..", "brands")
    for b in ("_default", "teletracking"):
        with open(os.path.join(root, b, "glossary.json"), encoding="utf-8") as fh:
            data = json.load(fh)
        assert isinstance(data.get("preferred"), list)
        assert isinstance(data.get("banned"), list)
