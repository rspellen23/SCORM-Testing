"""Deck PURPOSE presets — purpose-specific profiles (formal / debrief / workshop /
client / pitch) shape a generated deck's STRUCTURE, VOICE, and LENGTH via a
prompt-layer injection only. Every preset uses the same on-brand layouts; the
difference is structure and tone, never divergent styling.

These assert the injection is present for each preset, absent for the neutral
default, robust to junk input, and that the dashboard's selector can't drift from
the canonical preset table.
"""
import os
import authoring as A

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def _prompt(preset):
    return A.build_deck_prompt("T", "", "", None, "SOURCE TEXT", preset=preset)


def test_general_and_unknown_inject_nothing():
    for preset in ("general", None, "", "nonsense"):
        p = _prompt(preset)
        assert "PRESENTATION PURPOSE" not in p
        # the core prompt still assembles
        assert "SOURCE TEXT" in p and '"slides"' in p


def test_every_real_preset_injects_label_arc_and_tone():
    for key, spec in A.DECK_PRESETS.items():
        if key == "general":
            continue
        p = _prompt(key)
        assert "PRESENTATION PURPOSE" in p
        assert spec["label"] in p
        assert "RECOMMENDED ARC" in p and "VOICE & TONE" in p
        assert spec["slides"] in p          # length hint present


def test_presets_differ_in_voice():
    # two different purposes must produce materially different directives
    assert _preset_block("pitch") != _preset_block("workshop")
    assert "learner" in _prompt("workshop").lower()
    assert "persuasive" in _prompt("pitch").lower()


def _preset_block(key):
    return A._preset_directive(key)


def test_directive_is_robust_to_bad_input():
    for junk in (None, "", "xyz", 123, {}, []):
        assert A._preset_directive(junk) == "" or isinstance(A._preset_directive(junk), str)


def test_dashboard_selector_matches_preset_table():
    """Drift guard: every DECK_PRESETS key must appear as an <option> in the slide
    tab's #sl_preset selector, and vice-versa — so the UI can't list a preset the
    backend doesn't honor (or omit one it does)."""
    html = open(os.path.join(REPO, "dashboard", "index.html"), encoding="utf-8").read()
    sel = html.split('id="sl_preset"', 1)[1].split("</select>", 1)[0]
    import re
    opts = set(re.findall(r'<option value="([^"]*)"', sel))
    assert opts == set(A.DECK_PRESETS), (opts, set(A.DECK_PRESETS))
