"""Taste / anti-slop discipline (distilled from the taste-skill principles,
inverted for the locked brand system).

authoring.TASTE_RULE is the condensed rule injected into BOTH the course and the
deck generation prompts. These tests pin that the rule carries the load-bearing
anti-slop signals and that it actually reaches each assembled prompt — the same
contract the CHART_RULE injection tests use.
"""
import authoring


def test_taste_rule_carries_the_load_bearing_signals():
    t = authoring.TASTE_RULE.lower()
    # anti-sameness / variety inside the locked system
    assert "vary" in t and "accent" in t
    # cut ruthlessly + the no-split-visualization rule
    assert "one idea per slide" in t
    assert "split" in t
    # at least some of the banned filler verbs are named
    assert "seamless" in t and "leverage" in t
    # no fake-precise numbers
    assert "fake-precise" in t or "literally in the source" in t
    # quote attribution discipline
    assert "role" in t


def test_course_prompt_injects_taste_rule():
    prompt = authoring.build_prompt("obj", "aud", "concept-explainer", 2, "some source text")
    assert "TASTE" in prompt
    # a representative banned-filler word makes it into the assembled prompt
    assert "seamless" in prompt.lower()


def test_deck_prompt_injects_taste_rule():
    prompt = authoring.build_deck_prompt("Title", "focus", "aud", 6, "some source text")
    assert "taste" in prompt.lower()
    assert "seamless" in prompt.lower()


def test_taste_rule_is_brand_faithful_not_high_variance():
    # the inversion: it must tell the model NOT to invent fonts/colors/layouts,
    # the opposite of the source skill's high-variance default.
    t = authoring.TASTE_RULE.lower()
    assert "never invent" in t
    assert "fixed" in t
