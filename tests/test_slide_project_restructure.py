"""Slide builder: it gained a full Project step (shared with the course tab — a
project holds both course and deck work), the define questions lead, sourcing +
generate follow, and the deck saves into the project root (so the old File-name /
Save-folder fields are gone; the name comes from the presentation title).

Static drift guards over the dashboard wiring.
"""
import os
import re

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
HTML = open(os.path.join(REPO, "dashboard", "index.html"), encoding="utf-8").read()


def _stage(stage_id):
    body = HTML.split(f'id="{stage_id}"', 1)[1]
    return body.split("<!-- P", 1)[0]


def _fn(name):
    return HTML.split(f"function {name}(", 1)[1].split("\n}", 1)[0]


def _slide_steps():
    line = re.search(r"const SLIDE_STEPS=\[(.*?)\];", HTML).group(1)
    return re.findall(r"'([^']*)'", line)   # labels can contain commas, so match quotes


def test_slide_steps_lead_with_project_then_source():
    steps = _slide_steps()
    assert steps[0] == "Project & define"
    assert steps[1] == "Source & generate"


def test_build_merged_into_review_step():
    # the standalone Build stage is gone; Review is the last step
    steps = _slide_steps()
    assert steps[-1] == "Review, edit & build" and len(steps) == 3
    assert 'id="ps3"' not in HTML
    ids = re.search(r"\? \[.*?\] : \[(.*?)\]", HTML).group(1)
    assert "ps3" not in ids
    # the build controls + button now live in the Review stage (ps2)
    ps2 = _stage("ps2")
    for fid in ("sl_transition", "sl_animate", "sl_go", "deck_list"):
        assert f'id="{fid}"' in ps2, fid


def test_project_step_has_picker_and_define_fields():
    ps = _stage("ps_proj")
    for fid in ("sl_ws", "sl_newproj", "sl_projlist", "sl_title", "sl_focus",
                "sl_aud", "sl_preset", "sl_n"):
        assert f'id="{fid}"' in ps, fid
    # the picker drives the shared project functions from the slide tab
    assert "setWorkspace('sl_ws')" in ps and "openProject('sl_projlist')" in ps


def test_source_step_keeps_sources_and_generate():
    ps1 = _stage("ps1")
    assert 'id="sl_src"' in ps1 and 'id="sl_gen"' in ps1
    # the define fields are NOT duplicated back into the source step
    assert 'id="sl_title"' not in ps1 and 'id="sl_focus"' not in ps1


def test_deck_saves_to_project_root_no_folder_picker():
    assert "sl_out" not in HTML and "sl_name" not in HTML
    bd = _fn("buildDeck")
    assert "out:CURRENT_PROJECT" in bd
    assert "name:val('sl_title')" in bd
    assert "if(!CURRENT_PROJECT)" in bd            # building needs a project


def test_generate_requires_a_project():
    gd = _fn("genDeck")
    assert "if(!CURRENT_PROJECT)" in gd


def test_project_meta_persists_and_restores_deck_fields():
    sp = _fn("saveProject")
    for key in ("sl_title:", "sl_focus:", "sl_aud:", "sl_n:", "sl_preset:", "deck:DECK"):
        assert key in sp, key
    lp = _fn("loadProject")
    assert "m.sl_title" in lp and "m.deck" in lp


def test_projchip_visible_in_both_tabs():
    sm = _fn("setMode")
    # the projchip is no longer hidden in slide mode — its display is set unconditionally
    assert re.search(r"getElementById\('projchip'\)\.style\.display\s*=\s*''", sm)
    assert not re.search(r"getElementById\('projchip'\)\.style\.display\s*=\s*slide", sm)
